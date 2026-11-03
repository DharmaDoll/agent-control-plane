"""Isolated artifact tests. These do not exercise a Claude Code runtime."""

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "claude_harden", Path(__file__).parents[1] / "scripts" / "harden.py")
harden = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harden)


@unittest.skipUnless(os.name == "posix", "POSIX artifact helper")
class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="acp-claude-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"
        self.output_dir = self.root / "candidates"
        for path in (self.home, self.workspace, self.output_dir):
            path.mkdir(mode=0o700)
        self.output = self.output_dir / "development.candidate.json"

    def arguments(self, command="plan", **updates):
        values = dict(command=command, workspace=str(self.workspace),
                      user_home=str(self.home), mode="development",
                      output=str(self.output), plan_id=None, claude_version="unknown")
        values.update(updates)
        return argparse.Namespace(**values)

    def plan(self, **updates):
        return harden.operate(self.arguments(**updates))

    def export(self, **updates):
        plan = self.plan(**updates)
        return harden.operate(self.arguments("export", plan_id=plan["plan_id"], **updates))

    def private_file(self, path, data=b"unrelated-secret-value"):
        path.write_bytes(data)
        path.chmod(0o600)

    def test_plan_deterministic_and_read_only(self):
        before = sorted(self.root.rglob("*"))
        first = self.plan()
        self.assertEqual(first, self.plan())
        self.assertEqual(sorted(self.root.rglob("*")), before)
        self.assertFalse(self.output.exists())
        self.assertEqual(first["runtime"], "NOT_VERIFIED")

    def test_export_then_verify_both_modes(self):
        for mode in ("review", "development"):
            with self.subTest(mode=mode):
                output = self.output_dir / f"{mode}.json"
                result = self.export(mode=mode, output=str(output))
                self.assertEqual(result["status"], "CANDIDATE_EXPORTED")
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                self.assertEqual(output.stat().st_nlink, 1)
                verified = harden.operate(self.arguments("verify", mode=mode, output=str(output)))
                self.assertEqual(verified["status"], "ARTIFACT_MATCH")
                self.assertEqual(verified["runtime"], "NOT_VERIFIED")
        self.assertEqual(sorted(p.name for p in self.output_dir.iterdir()),
                         ["development.json", "review.json"])

    def test_existing_output_never_overwritten(self):
        self.private_file(self.output)
        original = self.output.read_bytes()
        plan = self.plan()
        with self.assertRaisesRegex(harden.Refusal, "OUTPUT_EXISTS"):
            harden.operate(self.arguments("export", plan_id=plan["plan_id"]))
        self.assertEqual(self.output.read_bytes(), original)

    def test_export_remains_private_under_unusual_umask(self):
        previous = os.umask(0o777)
        try:
            self.export()
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(harden.operate(self.arguments("verify"))["status"], "ARTIFACT_MATCH")

    def test_stale_plan_when_output_appears(self):
        plan = self.plan()
        self.private_file(self.output)
        with self.assertRaisesRegex(harden.Refusal, "STALE_PLAN"):
            harden.operate(self.arguments("export", plan_id=plan["plan_id"]))

    def test_stale_plan_when_options_change(self):
        plan = self.plan()
        for changes in ({"mode": "review"}, {"claude_version": "2.1.290"},
                        {"output": str(self.output_dir / "second.json")}):
            with self.subTest(changes=changes), self.assertRaisesRegex(harden.Refusal, "STALE_PLAN"):
                harden.operate(self.arguments("export", plan_id=plan["plan_id"], **changes))
        self.assertFalse(self.output.exists())

    def test_source_changes_invalidate_plan(self):
        plan = self.plan()
        with mock.patch.object(Path, "read_bytes", return_value=b"new generator source"):
            with self.assertRaisesRegex(harden.Refusal, "STALE_PLAN"):
                harden.operate(self.arguments("export", plan_id=plan["plan_id"]))

    def test_workspace_replaced_invalidates_plan(self):
        plan = self.plan()
        self.workspace.rename(self.root / "original-workspace")
        self.workspace.mkdir()
        with self.assertRaisesRegex(harden.Refusal, "STALE_PLAN"):
            harden.operate(self.arguments("export", plan_id=plan["plan_id"]))

    def test_plan_binds_existing_bytes(self):
        self.private_file(self.output, b"first")
        first = self.plan()
        self.private_file(self.output, b"second")
        self.assertNotEqual(self.plan()["plan_id"], first["plan_id"])

    def test_tampered_artifact_fails_verification(self):
        self.export()
        settings = json.loads(self.output.read_text())
        settings["sandbox"]["enabled"] = False
        self.output.write_text(json.dumps(settings))
        with self.assertRaisesRegex(harden.Refusal, "ARTIFACT_MISMATCH"):
            harden.operate(self.arguments("verify"))

    def test_missing_artifact_fails_verification(self):
        with self.assertRaisesRegex(harden.Refusal, "ARTIFACT_MISSING"):
            harden.operate(self.arguments("verify"))

    def test_mode_mismatch_fails_verification(self):
        self.export()
        with self.assertRaisesRegex(harden.Refusal, "ARTIFACT_MISMATCH"):
            harden.operate(self.arguments("verify", mode="review"))

    def test_unsafe_paths_rejected(self):
        cases = ("relative", str(self.workspace) + "/", str(self.workspace) + "/../workspace",
                 str(self.workspace) + "\nsecret", str(self.workspace) + "*",
                 str(self.workspace) + "/[abc]", "//" + str(self.workspace).lstrip("/"))
        for path in cases:
            with self.subTest(path=path), self.assertRaisesRegex(harden.Refusal, "UNSAFE_PATH"):
                self.plan(workspace=path)

    def test_spaces_in_paths_are_literal(self):
        spaced = self.root / "workspace with spaces"
        spaced.mkdir()
        plan = self.plan(workspace=str(spaced))
        self.assertEqual(plan["workspace"], str(spaced))
        self.export(workspace=str(spaced))

    def test_symlink_directory_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(OSError):
            self.plan(workspace=str(alias))

    def test_symlink_output_parent_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.output_dir, target_is_directory=True)
        with self.assertRaises(OSError):
            self.plan(output=str(alias / "candidate.json"))

    def test_symlink_and_dangling_output_rejected(self):
        for target in (self.root / "missing", self.home):
            with self.subTest(target=target):
                self.output.symlink_to(target)
                with self.assertRaises(OSError):
                    self.plan()
                self.output.unlink()

    def test_fifo_output_rejected_without_blocking(self):
        os.mkfifo(self.output, 0o600)
        with self.assertRaisesRegex(harden.Refusal, "UNSAFE_OUTPUT_FILE"):
            self.plan()

    def test_hardlinked_output_rejected(self):
        original = self.root / "original"
        self.private_file(original)
        os.link(original, self.output)
        with self.assertRaisesRegex(harden.Refusal, "UNSAFE_OUTPUT_FILE"):
            self.plan()

    def test_public_output_rejected(self):
        self.private_file(self.output)
        self.output.chmod(0o644)
        with self.assertRaisesRegex(harden.Refusal, "UNSAFE_OUTPUT_FILE"):
            self.plan()

    def test_writable_output_parent_rejected(self):
        self.output_dir.chmod(0o777)
        with self.assertRaisesRegex(harden.Refusal, "UNSAFE_OUTPUT_PARENT"):
            self.plan()

    def test_oversized_output_rejected(self):
        self.private_file(self.output, b"x" * (harden.MAX_BYTES + 1))
        with self.assertRaisesRegex(harden.Refusal, "OUTPUT_TOO_LARGE"):
            self.plan()

    def test_active_settings_names_rejected(self):
        for name in ("settings.json", "settings.local.json", "managed-settings.json", ".mcp.json", "candidate.txt"):
            with self.subTest(name=name), self.assertRaisesRegex(harden.Refusal, "OUTPUT_MUST_BE_CANDIDATE_JSON"):
                self.plan(output=str(self.output_dir / name))

    def test_automatic_loading_directories_rejected(self):
        for name in (".claude", "managed-settings.d"):
            with self.subTest(name=name), self.assertRaisesRegex(harden.Refusal, "OUTPUT_MUST_BE_CANDIDATE_JSON"):
                self.plan(output=str(self.home / name / "candidate.json"))

    def test_output_inside_workspace_rejected(self):
        with self.assertRaisesRegex(harden.Refusal, "OUTPUT_INSIDE_WORKSPACE"):
            self.plan(output=str(self.workspace / "candidate.json"))

    def test_workspace_containing_home_rejected(self):
        for workspace in (self.home, self.root):
            with self.subTest(workspace=workspace), self.assertRaisesRegex(harden.Refusal, "WORKSPACE_CONTAINS_HOME"):
                self.plan(workspace=str(workspace))

    def test_protected_locations_rejected_without_reading(self):
        with self.assertRaisesRegex(harden.Refusal, "PROTECTED_WORKSPACE"):
            self.plan(workspace=str(self.home / ".aws" / "project"))
        for path in (self.home / ".claude.json", self.home / ".aws" / "candidate.json"):
            with self.subTest(path=path), self.assertRaisesRegex(harden.Refusal, "PROTECTED_OUTPUT"):
                self.plan(output=str(path))

    def test_export_publication_race_never_clobbers(self):
        real_link = os.link
        def raced_link(source, destination, **kwargs):
            self.private_file(self.output, b"concurrent-writer")
            return real_link(source, destination, **kwargs)
        with mock.patch.object(os, "link", side_effect=raced_link), self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(self.output.read_bytes(), b"concurrent-writer")
        self.assertEqual(list(self.output_dir.iterdir()), [self.output])

    def test_failed_publication_cleans_temporary_file(self):
        with mock.patch.object(os, "link", side_effect=OSError("private error")), self.assertRaises(OSError):
            self.export()
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_sandbox_escape_and_autonomy_disabled(self):
        settings = self.plan()["settings"]
        sandbox = settings["sandbox"]
        self.assertTrue(sandbox["enabled"])
        self.assertTrue(sandbox["failIfUnavailable"])
        self.assertFalse(sandbox["allowUnsandboxedCommands"])
        self.assertFalse(sandbox["autoAllowBashIfSandboxed"])
        self.assertFalse(sandbox["filesystem"]["disabled"])
        self.assertEqual(settings["disableAutoMode"], "disable")
        self.assertFalse(settings["useAutoModeDuringPlan"])
        self.assertEqual(settings["permissions"]["disableBypassPermissionsMode"], "disable")
        for tool in ("Bash", "PowerShell", "Monitor", "Edit", "Write", "NotebookEdit"):
            self.assertIn(tool, settings["permissions"]["ask"])
        self.assertIn("Agent", settings["permissions"]["deny"])

    def test_review_has_no_shell_or_file_modification_tools(self):
        permissions = self.plan(mode="review")["settings"]["permissions"]
        for tool in ("Bash", "PowerShell", "Monitor", "Edit", "Write", "NotebookEdit", "Agent"):
            self.assertIn(tool, permissions["deny"])
        self.assertNotIn("Read", permissions["deny"])
        self.assertNotIn("Bash", self.plan()["settings"]["permissions"]["deny"])

    def test_home_secrets_protected_in_both_layers(self):
        settings = self.plan()["settings"]
        for suffix in (".ssh", ".aws", ".claude.json", ".claude/.credentials.json"):
            path = self.home / suffix
            self.assertIn(str(path), settings["sandbox"]["filesystem"]["denyRead"])
            self.assertIn(str(path), settings["sandbox"]["filesystem"]["denyWrite"])
            self.assertIn(f"Read(/{path})", settings["permissions"]["deny"])
            self.assertIn(f"Edit(/{path})", settings["permissions"]["deny"])

    def test_cli_errors_do_not_disclose_content_or_input(self):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = harden.main(["plan", "--private-secret-argument"])
        self.assertEqual(code, 2)
        self.assertNotIn("private-secret", capture.getvalue())
        self.assertEqual(json.loads(capture.getvalue())["reason"], "INVALID_ARGUMENTS")
        arguments = ["plan", "--workspace", str(self.workspace), "--user-home", str(self.home),
                     "--mode", "development", "--output", str(self.output)]
        capture = io.StringIO()
        with mock.patch.object(harden, "operate", side_effect=OSError("synthetic-SECRET")):
            with contextlib.redirect_stdout(capture):
                self.assertEqual(harden.main(arguments), 2)
        self.assertNotIn("synthetic-SECRET", capture.getvalue())
        self.assertEqual(json.loads(capture.getvalue())["reason"], "FILESYSTEM_ERROR")

    def test_version_is_metadata_only_and_validated(self):
        plan = self.plan(claude_version="2.1.290")
        self.assertEqual(plan["claude_version"], "2.1.290")
        self.assertNotIn("claude_version", plan["settings"])
        self.assertEqual(plan["runtime"], "NOT_VERIFIED")
        with self.assertRaisesRegex(harden.Refusal, "INVALID_CLAUDE_VERSION"):
            self.plan(claude_version="latest")

    def run_cli(self, arguments):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            result = harden.main(arguments)
        return result, json.loads(capture.getvalue())

    def test_samples_lists_scenarios_without_inspecting_files(self):
        with mock.patch.object(harden, "directory", side_effect=AssertionError("filesystem access")):
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("file read")):
                code, result = self.run_cli(["samples"])
        self.assertEqual(code, 0)
        self.assertEqual(result["runtime"], "NOT_VERIFIED")
        samples = {sample["sample_id"]: sample for sample in result["samples"]}
        self.assertEqual(set(samples), {"code-review", "local-development", "npm-dependencies", "pypi-dependencies"})
        self.assertEqual(samples["local-development"]["additional_domains"], [])
        self.assertEqual(samples["npm-dependencies"]["additional_domains"], ["registry.npmjs.org"])
        for sample in samples.values():
            self.assertTrue(sample["summary"])
            self.assertTrue(sample["limitations"])

    def test_all_samples_complete_lifecycle(self):
        expected_domains = {
            "code-review": [], "local-development": [],
            "npm-dependencies": ["registry.npmjs.org"],
            "pypi-dependencies": ["pypi.org", "files.pythonhosted.org"],
        }
        for sample, domains in expected_domains.items():
            with self.subTest(sample=sample):
                options = dict(sample=sample, mode=None, output=str(self.output_dir / (sample + ".json")))
                plan = self.plan(**options)
                self.assertEqual(plan["sample_id"], sample)
                self.assertEqual(plan["sample"]["additional_domains"], domains)
                self.assertEqual(plan["settings"]["sandbox"]["network"]["allowedDomains"], domains)
                self.assertFalse(Path(options["output"]).exists())
                self.assertEqual(self.export(**options)["sample_id"], sample)
                verified = harden.operate(self.arguments("verify", **options))
                self.assertEqual(verified["sample_id"], sample)
                self.assertEqual(verified["status"], "ARTIFACT_MATCH")
                self.assertEqual(verified["runtime"], "NOT_VERIFIED")

    def test_dependency_samples_change_only_explicit_domains(self):
        baseline = self.plan()["settings"]
        for sample in ("npm-dependencies", "pypi-dependencies"):
            with self.subTest(sample=sample):
                candidate = self.plan(mode=None, sample=sample)["settings"]
                self.assertNotEqual(candidate, baseline)
                candidate["sandbox"]["network"]["allowedDomains"] = []
                self.assertEqual(candidate, baseline)

    def test_legacy_modes_keep_setting_bytes_and_resolve_to_same_plan(self):
        # Captured from the pre-selector implementation with these fixed paths.
        fingerprints = {
            "review": "88c855c3b3fa24f9a129cc85369ddcfd9d437ca031d6726250dfcc3e0f860532",
            "development": "bdb4f021140f1880f813845b231b05038545bc2cb57730b5a4ef9993fa57a4bf",
        }
        for mode, sample in (("review", "code-review"), ("development", "local-development")):
            with self.subTest(mode=mode):
                settings = harden.build_settings(Path('/example/workspace'), Path('/example/home'), mode)
                self.assertEqual(harden.digest(harden.encode(settings)), fingerprints[mode])
                self.assertEqual(self.plan(mode=mode), self.plan(mode=None, sample=sample))

    def test_sample_change_invalidates_plan_with_same_mode(self):
        plan = self.plan(mode=None, sample="local-development")
        with self.assertRaisesRegex(harden.Refusal, "STALE_PLAN"):
            harden.operate(self.arguments("export", mode=None, sample="npm-dependencies", plan_id=plan["plan_id"]))
        self.assertFalse(self.output.exists())

    def test_different_dependency_sample_fails_verification(self):
        self.export(mode=None, sample="npm-dependencies")
        with self.assertRaisesRegex(harden.Refusal, "ARTIFACT_MISMATCH"):
            harden.operate(self.arguments("verify", mode=None, sample="pypi-dependencies"))

    def test_cli_rejects_unknown_ambiguous_and_missing_sample(self):
        base = ["plan", "--workspace", str(self.workspace), "--user-home", str(self.home),
                "--output", str(self.output)]
        for selection in ([], ["--sample", "private-secret-sample"],
                          ["--sample", "npm-dependencies", "--mode", "development"]):
            with self.subTest(selection=selection):
                code, result = self.run_cli(base + selection)
                self.assertEqual(code, 2)
                self.assertEqual(result["reason"], "INVALID_ARGUMENTS")
                self.assertNotIn("private-secret", json.dumps(result))
        self.assertFalse(self.output.exists())

    def test_samples_rejects_operation_flags(self):
        for options in (["--workspace", str(self.workspace)], ["--sample", "code-review"],
                        ["--claude-version", "2.1.290"], ["--output", str(self.output)]):
            with self.subTest(options=options):
                code, result = self.run_cli(["samples"] + options)
                self.assertEqual(code, 2)
                self.assertEqual(result["reason"], "INVALID_ARGUMENTS")

    def test_cli_sample_plan_exports_and_verifies(self):
        options = ["--workspace", str(self.workspace), "--user-home", str(self.home),
                   "--output", str(self.output), "--sample", "pypi-dependencies"]
        code, plan = self.run_cli(["plan"] + options)
        self.assertEqual(code, 0)
        code, result = self.run_cli(["export"] + options + ["--plan-id", plan["plan_id"]])
        self.assertEqual(code, 0)
        self.assertEqual(result["sample_id"], "pypi-dependencies")
        code, result = self.run_cli(["verify"] + options)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ARTIFACT_MATCH")


if __name__ == "__main__":
    unittest.main()
