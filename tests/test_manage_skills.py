"""Offline contract tests for the repository's skill distribution helper.

All repositories, installation roots, and process-interruption artifacts live in
an explicitly selected directory inside this checkout. No network or active
agent configuration is used.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "manage_skills.py"
REPOSITORY = "DharmaDoll/agent-control-plane"
NAMES = (
    "spec-driven-development",
    "controlled-github",
    "secret-checks",
    "codex-hardening",
    "claude-code-hardening",
)


class InstallationContractTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(
            prefix=".skill-install-test-", dir=ROOT
        )
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.work = self.root / "acquisition"
        self.work.mkdir()
        self.source = self.work / "source"
        self.source.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        self.dest = self.project / ".claude" / "skills"
        self.manifest = self.work / "skills-install.json"
        self.env = os.environ.copy()
        for key in tuple(self.env):
            if key.startswith("GIT_"):
                self.env.pop(key)
        self.env.update(
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.git("init", "--quiet")
        self.git("remote", "add", "origin", f"https://github.com/{REPOSITORY}.git")
        (self.source / "scripts").mkdir()
        (self.source / "scripts" / "manage_skills.py").write_bytes(HELPER.read_bytes())
        self.originals = {}
        for name in NAMES:
            base = self.source / "skills" / name
            (base / "references").mkdir(parents=True)
            (base / "scripts").mkdir()
            contents = (
                f"---\nname: {name}\ndescription: Synthetic fixture.\n---\n"
                "\nRead [notes](references/notes.md).\n"
            ).encode()
            (base / "SKILL.md").write_bytes(contents)
            (base / "references" / "notes.md").write_text("Fixture reference.\n")
            probe = base / "scripts" / "probe.py"
            probe.write_text(
                "from pathlib import Path\n"
                "Path('downloaded-script-ran').write_text('unexpected execution')\n"
            )
            probe.chmod(0o755)
            self.originals[name] = contents
        self.sha = self.commit()

    def git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.source), *args],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout.decode().strip()

    def commit(self):
        self.git("add", "--", "scripts/manage_skills.py", "skills")
        self.git(
            "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture"
        )
        return self.git("rev-parse", "HEAD")

    def arguments(self, *names, dest=None, manifest=None, sha=None):
        args = [
            "install", "--source", str(self.source),
            "--commit", sha or self.sha,
            "--dest", str(dest or self.dest),
            "--manifest", str(manifest or self.manifest),
        ]
        if names:
            for name in names:
                args.extend(["--skill", name])
        else:
            args.append("--all")
        return args

    def run_cli(self, args, expected=0, env=None):
        result = subprocess.run(
            [sys.executable, "-B", str(HELPER), *args],
            cwd=self.root, env=env or self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertTrue(result.stdout.strip(), result.stderr)
        report = json.loads(result.stdout)
        self.assertIsInstance(report, dict)
        return report

    def install(self, *names, expected=0, **kwargs):
        return self.run_cli(self.arguments(*names, **kwargs), expected=expected)

    def verify(self, expected=0, manifest=None):
        return self.run_cli(
            ["verify", "--manifest", str(manifest or self.manifest)], expected
        )

    def rows(self, report):
        return {item["name"]: item for item in report["skills"]}

    def module(self):
        spec = importlib.util.spec_from_file_location("installation_fixture_helper", HELPER)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        self.addCleanup(sys.modules.pop, spec.name, None)
        return module

    def call_main(self, module, args, expected):
        stream = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True):
            with contextlib.redirect_stdout(stream):
                code = module.main(args)
        self.assertEqual(code, expected, stream.getvalue())
        return json.loads(stream.getvalue())

    def test_all_five_for_both_agent_roots(self):
        for agent in (".agents", ".claude"):
            with self.subTest(agent=agent):
                dest = self.project / agent / "skills"
                manifest = self.work / f"skills-install-{agent[1:]}.json"
                report = self.install(dest=dest, manifest=manifest)
                self.assertEqual(report["status"], "PASS")
                self.assertEqual(set(self.rows(report)), set(NAMES))
                self.assertEqual({r["status"] for r in report["skills"]}, {"MATCH"})
                self.assertEqual({r["action"] for r in report["skills"]}, {"COPIED"})
                for name in NAMES:
                    self.assertEqual((dest / name / "SKILL.md").read_bytes(), self.originals[name])
                    self.assertTrue((dest / name / "scripts" / "probe.py").stat().st_mode & 0o111)
                self.assertEqual(set(p.name for p in dest.parent.iterdir()), {"skills"})
                self.assertEqual(self.verify(manifest=manifest)["status"], "PASS")
        self.assertFalse((self.root / "downloaded-script-ran").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_sibling_manifest_remains_supported_when_explicitly_selected(self):
        self.dest.parent.mkdir()
        sibling = self.dest.parent / "skills-install.json"
        self.install("controlled-github", manifest=sibling)
        self.assertEqual(self.verify(manifest=sibling)["status"], "PASS")
        self.assertEqual(set(p.name for p in self.dest.parent.iterdir()), {"skills", "skills-install.json"})

    def test_successful_workflow_cleanup_leaves_only_the_skills(self):
        acquired_helper = self.work / "manage_skills.py"
        acquired_helper.write_bytes(HELPER.read_bytes())
        for arguments in (self.arguments(), ["verify", "--manifest", str(self.manifest)]):
            result = subprocess.run(
                [sys.executable, "-B", str(acquired_helper), *arguments],
                cwd=self.root, env=self.env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
            self.assertEqual(json.loads(result.stdout)["status"], "PASS")
        shutil.rmtree(self.work)
        self.assertEqual(list(self.root.iterdir()), [self.project])
        self.assertEqual(set(p.name for p in self.dest.parent.iterdir()), {"skills"})
        self.assertEqual(set(p.name for p in self.dest.iterdir()), set(NAMES))
        self.assertEqual(list(self.project.rglob("skills-install*.json")), [])
        self.assertEqual(list(self.project.rglob("manage_skills.py")), [])
        for name in NAMES:
            self.assertEqual((self.dest / name / "SKILL.md").read_bytes(), self.originals[name])

    def test_subset_has_no_extra_skills(self):
        selected = ("controlled-github", "spec-driven-development")
        report = self.install(*selected)
        self.assertEqual(set(self.rows(report)), set(selected))
        self.assertEqual(set(p.name for p in self.dest.iterdir()), set(selected))

    def test_manifest_records_expected_commit_and_independent_hashes(self):
        self.install("controlled-github")
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["repository"], REPOSITORY)
        self.assertEqual(manifest["commit"], self.sha)
        self.assertEqual(manifest["destination"], str(self.dest))
        self.assertEqual(manifest["helper_sha256"], hashlib.sha256(HELPER.read_bytes()).hexdigest())
        files = {entry["path"]: entry for entry in manifest["skills"][0]["files"]}
        self.assertEqual(files["SKILL.md"]["sha256"], hashlib.sha256(self.originals["controlled-github"]).hexdigest())
        self.assertEqual(files["SKILL.md"]["size"], len(self.originals["controlled-github"]))
        self.assertFalse(files["SKILL.md"]["executable"])
        self.assertTrue(files["scripts/probe.py"]["executable"])
        self.assertNotIn("status", manifest)
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o600)

    def test_dirty_worktree_and_new_head_do_not_change_pinned_bytes(self):
        base = self.source / "skills" / "controlled-github"
        (base / "SKILL.md").write_text("new committed version\n")
        newer = self.commit()
        self.assertNotEqual(newer, self.sha)
        (base / "SKILL.md").write_text("uncommitted version\n")
        (base / "untracked.txt").write_text("do not copy")
        (self.source / "scripts" / "manage_skills.py").write_text("dirty helper")
        self.install("controlled-github")
        self.assertEqual((self.dest / "controlled-github" / "SKILL.md").read_bytes(), self.originals["controlled-github"])
        self.assertFalse((self.dest / "controlled-github" / "untracked.txt").exists())

    def test_helper_mismatch_blocks_before_manifest_or_copy(self):
        (self.source / "scripts" / "manage_skills.py").write_text("# other helper\n")
        other = self.commit()
        report = self.install("controlled-github", sha=other, expected=2)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_invalid_commit_blocks_without_copy(self):
        for sha in ("main", "HEAD", "-bad", "f" * 40):
            with self.subTest(sha=sha):
                self.install("controlled-github", sha=sha, expected=2)
                self.assertFalse(self.dest.exists())

    def test_wrong_origin_blocks_without_copy(self):
        self.git("remote", "set-url", "origin", "https://github.com/example/other.git")
        self.install("controlled-github", expected=2)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_source_symlink_is_rejected_before_any_copy(self):
        (self.source / "skills" / "secret-checks" / "alias").symlink_to("SKILL.md")
        other = self.commit()
        self.install(sha=other, expected=2)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_source_gitlink_is_rejected_before_any_copy(self):
        self.git("update-index", "--add", "--cacheinfo", "160000", self.sha, "skills/secret-checks/nested")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "gitlink fixture")
        self.install(sha=self.git("rev-parse", "HEAD"), expected=2)
        self.assertFalse(self.dest.exists())

    def test_control_character_source_path_is_rejected(self):
        (self.source / "skills" / "controlled-github" / "bad\nname").write_text("invalid name")
        self.install("controlled-github", sha=self.commit(), expected=2)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_source_case_collision_is_rejected(self):
        (self.source / "skills" / "controlled-github" / "references" / "NOTES.md").write_text("case collision")
        self.install("controlled-github", sha=self.commit(), expected=2)
        self.assertFalse(self.dest.exists())

    def test_git_lfs_pointer_is_not_copied_as_actual_payload(self):
        (self.source / "skills" / "controlled-github" / "payload.bin").write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "0" * 64 + "\nsize 100\n"
        )
        self.install("controlled-github", sha=self.commit(), expected=2)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_missing_later_skill_file_prevents_entire_batch_copy(self):
        (self.source / "skills" / "secret-checks" / "SKILL.md").unlink()
        other = self.commit()
        self.install(sha=other, expected=2)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_existing_partial_skill_is_skipped_without_repair(self):
        existing = self.dest / "controlled-github"
        existing.mkdir(parents=True)
        sentinel = existing / "SKILL.md"
        sentinel.write_bytes(b"user-owned content")
        report = self.install(expected=1)
        row = self.rows(report)["controlled-github"]
        self.assertEqual(row["action"], "SKIPPED_EXISTING")
        self.assertNotEqual(row["status"], "MATCH")
        self.assertEqual(sentinel.read_bytes(), b"user-owned content")
        self.assertEqual(list(existing.iterdir()), [sentinel])
        self.assertEqual(sum(row["status"] == "MATCH" for row in report["skills"]), 4)

    def test_existing_skill_file_is_not_replaced(self):
        self.dest.mkdir(parents=True)
        existing = self.dest / "controlled-github"
        existing.write_text("keep this file")
        report = self.install("controlled-github", expected=1)
        self.assertEqual(self.rows(report)["controlled-github"]["action"], "SKIPPED_EXISTING")
        self.assertEqual(existing.read_text(), "keep this file")

    def test_existing_skill_symlink_is_neither_followed_nor_replaced(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("untouched")
        self.dest.mkdir(parents=True)
        (self.dest / "controlled-github").symlink_to(outside, target_is_directory=True)
        report = self.install("controlled-github", expected=1)
        self.assertNotEqual(self.rows(report)["controlled-github"]["status"], "MATCH")
        self.assertEqual(list(outside.iterdir()), [sentinel])
        self.assertTrue((self.dest / "controlled-github").is_symlink())

    def test_destination_parent_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.dest.parent.symlink_to(outside, target_is_directory=True)
        self.install("controlled-github", expected=2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_identical_reinstall_is_unchanged(self):
        self.install()
        before = {str(p.relative_to(self.dest.parent)): (p.stat().st_ino, p.stat().st_mtime_ns)
                  for p in self.dest.parent.rglob("*")}
        record_before = (self.manifest.stat().st_ino, self.manifest.stat().st_mtime_ns,
                         self.manifest.read_bytes())
        report = self.install()
        self.assertEqual({r["action"] for r in report["skills"]}, {"SKIPPED_EXISTING"})
        after = {str(p.relative_to(self.dest.parent)): (p.stat().st_ino, p.stat().st_mtime_ns)
                 for p in self.dest.parent.rglob("*")}
        self.assertEqual(before, after)
        self.assertEqual((self.manifest.stat().st_ino, self.manifest.stat().st_mtime_ns,
                          self.manifest.read_bytes()), record_before)

    def test_different_existing_manifest_is_not_overwritten(self):
        self.manifest.write_text("existing record\n")
        self.install("controlled-github", expected=2)
        self.assertEqual(self.manifest.read_text(), "existing record\n")
        self.assertFalse(self.dest.exists())

    def test_manifest_symlink_is_not_followed(self):
        sentinel = self.root / "record"
        sentinel.write_text("existing record")
        self.manifest.symlink_to(sentinel)
        self.install("controlled-github", expected=2)
        self.assertEqual(sentinel.read_text(), "existing record")
        self.assertFalse(self.dest.exists())

    def test_external_manifest_parent_symlink_is_not_followed(self):
        actual = self.root / "record-directory"
        actual.mkdir()
        alias = self.root / "record-alias"
        alias.symlink_to(actual, target_is_directory=True)
        self.install("controlled-github", manifest=alias / "skills-install.json", expected=2)
        self.assertEqual(list(actual.iterdir()), [])
        self.assertFalse(self.dest.exists())

    def test_missing_external_manifest_parent_is_not_created(self):
        missing = self.root / "missing-record-directory"
        self.install("controlled-github", manifest=missing / "skills-install.json", expected=2)
        self.assertFalse(missing.exists())
        self.assertFalse(self.dest.exists())

    def test_manifest_write_interruption_prevents_skill_copy(self):
        module = self.module()
        original = module.write_file

        def fail_manifest(parent, name, data, mode):
            if name == self.manifest.name:
                original(parent, name, b'{"incomplete":', mode)
                raise OSError("injected record write failure")
            return original(parent, name, data, mode)

        with mock.patch.object(module, "write_file", side_effect=fail_manifest):
            self.call_main(module, self.arguments(), 2)
        self.assertEqual(self.manifest.read_bytes(), b'{"incomplete":')
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.verify(expected=2)["status"], "BLOCKED")

    def test_copy_error_keeps_manifest_and_partial_files_for_verify(self):
        module = self.module()
        observed = []

        def fail_copy(dest_fd, name, files, payloads):
            record = json.loads(self.manifest.read_text())
            self.assertEqual(record["commit"], self.sha)
            observed.append(name)
            os.mkdir(name, dir_fd=dest_fd)
            folder = self.dest / name
            (folder / "SKILL.md").write_bytes(b"partial copy")
            raise OSError("private diagnostic should not be echoed")

        with mock.patch.object(module, "copy_skill", side_effect=fail_copy):
            report = self.call_main(module, self.arguments("controlled-github"), 1)
        self.assertEqual(observed, ["controlled-github"])
        row = self.rows(report)["controlled-github"]
        self.assertEqual(row["action"], "COPY_FAILED")
        self.assertNotEqual(row["status"], "MATCH")
        self.assertNotIn("private diagnostic", json.dumps(report))
        shutil.rmtree(self.source)
        recorded = (self.manifest.read_bytes(), self.manifest.stat().st_mtime_ns)
        self.assertNotEqual(self.rows(self.verify(expected=1))["controlled-github"]["status"], "MATCH")
        self.assertEqual((self.manifest.read_bytes(), self.manifest.stat().st_mtime_ns), recorded)
        self.assertEqual((self.dest / "controlled-github" / "SKILL.md").read_bytes(), b"partial copy")

    def test_copy_error_cannot_be_hidden_by_matching_final_files(self):
        module = self.module()
        original = module.copy_skill

        def fail_after_copy(*args):
            original(*args)
            raise OSError("injected completion error")

        with mock.patch.object(module, "copy_skill", side_effect=fail_after_copy):
            report = self.call_main(module, self.arguments("controlled-github"), 1)
        self.assertEqual(report["status"], "INCOMPLETE")
        row = self.rows(report)["controlled-github"]
        self.assertEqual(row["action"], "COPY_FAILED")
        self.assertEqual(row["status"], "MATCH")
        self.assertEqual(self.verify()["status"], "PASS")

    def test_mid_copy_file_exists_error_is_not_an_existing_skill_skip(self):
        module = self.module()
        original = module.copy_skill

        def fail_after_copy(*args):
            original(*args)
            raise FileExistsError("injected nested collision")

        with mock.patch.object(module, "copy_skill", side_effect=fail_after_copy):
            report = self.call_main(module, self.arguments("controlled-github"), 1)
        row = self.rows(report)["controlled-github"]
        self.assertEqual(row["status"], "MATCH")
        self.assertEqual(row["action"], "COPY_FAILED")
        self.assertEqual(report["status"], "INCOMPLETE")

    def test_destination_creation_failure_reports_every_manifest_skill(self):
        module = self.module()
        original = module.descend

        def fail_destination(parent, parts, create=False):
            if create and parts == ("skills",):
                self.assertTrue(self.manifest.is_file())
                raise PermissionError("injected destination denial")
            return original(parent, parts, create=create)

        with mock.patch.object(module, "descend", side_effect=fail_destination):
            report = self.call_main(module, self.arguments(), 1)
        self.assertEqual(set(self.rows(report)), set(NAMES))
        self.assertEqual({r["action"] for r in report["skills"]}, {"NOT_ATTEMPTED"})
        self.assertEqual({r["status"] for r in report["skills"]}, {"MISSING"})
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.verify(expected=1)["status"], "INCOMPLETE")

    def test_skill_stat_error_is_reported_without_hiding_other_results(self):
        module = self.module()
        original = module.os.stat

        def fail_one_stat(path, *args, **kwargs):
            if path == "controlled-github" and kwargs.get("follow_symlinks") is False:
                raise PermissionError("injected stat denial")
            return original(path, *args, **kwargs)

        with mock.patch.object(module.os, "stat", side_effect=fail_one_stat):
            report = self.call_main(module, self.arguments(), 1)
        rows = self.rows(report)
        self.assertEqual(rows["controlled-github"]["action"], "COPY_FAILED")
        self.assertEqual(rows["controlled-github"]["status"], "MISSING")
        self.assertEqual(sum(r["status"] == "MATCH" for r in rows.values()), 4)
        self.assertEqual(self.verify(expected=1)["status"], "INCOMPLETE")

    def test_git_reads_disable_transports_without_changing_parent_environment(self):
        module = self.module()
        inherited = {
            "GIT_NO_LAZY_FETCH": "0", "GIT_ALLOW_PROTOCOL": "https:ssh:file",
            "GIT_OPTIONAL_LOCKS": "1", "GIT_TERMINAL_PROMPT": "1",
            "INSTALLATION_TEST_MARKER": "preserved",
        }
        completed = subprocess.CompletedProcess([], 0, b"fixture", b"")
        with mock.patch.dict(os.environ, inherited):
            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                self.assertEqual(module.git(self.source, "rev-parse", "HEAD"), b"fixture")
            child = run.call_args.kwargs["env"]
            self.assertEqual(child["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(child["GIT_ALLOW_PROTOCOL"], "")
            self.assertEqual(child["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(child["GIT_TERMINAL_PROMPT"], "0")
            self.assertEqual(child["INSTALLATION_TEST_MARKER"], "preserved")
            self.assertTrue(all(os.environ[key] == value for key, value in inherited.items()))

    def test_missing_promisor_blob_never_triggers_an_implicit_fetch(self):
        # A local mirror makes this a real Git lazy-fetch test without network
        # access. Without transport restrictions Git repairs the missing object
        # by fetching a promisor pack, making an allegedly offline install pass.
        mirror = self.root / "mirror.git"
        subprocess.run(
            ["git", "clone", "--quiet", "--bare", "--no-hardlinks", str(self.source), str(mirror)],
            env=self.env, check=True, capture_output=True,
        )
        oid = self.git("rev-parse", self.sha + ":skills/controlled-github/SKILL.md")
        loose = self.source / ".git" / "objects" / oid[:2] / oid[2:]
        loose.unlink()
        self.git("config", "extensions.partialClone", "origin")
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "remote.origin.partialclonefilter", "blob:none")
        self.git("config", f"url.{mirror.as_uri()}.insteadOf", f"https://github.com/{REPOSITORY}.git")
        packs = self.source / ".git" / "objects" / "pack"
        before = set(packs.iterdir())
        report = self.install("controlled-github", expected=2)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(set(packs.iterdir()), before)
        self.assertFalse(loose.exists())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_abrupt_exit_can_be_detected_without_source_checkout(self):
        runner = (
            "import importlib.util, os, sys\n"
            "s=importlib.util.spec_from_file_location('fixture_stop',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m)\n"
            "original=m.copy_skill\n"
            "def stop(*args):\n"
            " original(*args)\n"
            " os._exit(73)\n"
            "m.copy_skill=stop\n"
            "m.main(sys.argv[2:])\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", runner, str(HELPER), *self.arguments()],
            cwd=self.root, env=self.env, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertTrue(self.manifest.is_file())
        shutil.rmtree(self.source)
        report = self.verify(expected=1)
        self.assertEqual(sum(r["status"] == "MATCH" for r in report["skills"]), 1)
        self.assertEqual(sum(r["status"] == "MISSING" for r in report["skills"]), 4)

    def test_verify_detects_missing_changed_extra_and_mode_changes(self):
        self.install()
        (self.dest / NAMES[0] / "references" / "notes.md").unlink()
        (self.dest / NAMES[1] / "SKILL.md").write_text("modified\n")
        (self.dest / NAMES[2] / "extra.txt").write_text("extra\n")
        (self.dest / NAMES[3] / "scripts" / "probe.py").chmod(0o644)
        rows = self.rows(self.verify(expected=1))
        for name in NAMES[:4]:
            self.assertNotEqual(rows[name]["status"], "MATCH", name)
        self.assertEqual(rows[NAMES[4]]["status"], "MATCH")

    def test_verify_detects_extra_empty_directory(self):
        self.install("controlled-github")
        (self.dest / "controlled-github" / "extra").mkdir()
        self.assertNotEqual(self.rows(self.verify(expected=1))["controlled-github"]["status"], "MATCH")

    def test_verify_rejects_file_symlink_and_fifo(self):
        self.install("controlled-github", "secret-checks")
        path = self.dest / "controlled-github" / "SKILL.md"
        path.unlink()
        path.symlink_to(self.source / "skills" / "controlled-github" / "SKILL.md")
        fifo = self.dest / "secret-checks" / "SKILL.md"
        fifo.unlink()
        os.mkfifo(fifo)
        report = self.verify(expected=1)
        self.assertTrue(all(r["status"] != "MATCH" for r in report["skills"]))

    def test_verify_rejects_shared_hardlinked_file(self):
        self.install("controlled-github")
        path = self.dest / "controlled-github" / "SKILL.md"
        os.link(path, self.root / "shared-inode")
        self.assertEqual(self.rows(self.verify(expected=1))["controlled-github"]["status"], "UNREADABLE")

    @unittest.skipIf(os.geteuid() == 0, "root can read chmod-000 files")
    def test_verify_reports_unreadable_file(self):
        self.install("controlled-github")
        path = self.dest / "controlled-github" / "SKILL.md"
        path.chmod(0)
        self.addCleanup(path.chmod, 0o644)
        self.assertEqual(self.rows(self.verify(expected=1))["controlled-github"]["status"], "UNREADABLE")

    def test_verify_refuses_invalid_schema_and_path_escape(self):
        self.install("controlled-github")
        original = json.loads(self.manifest.read_text())
        invalid = []
        data = copy.deepcopy(original)
        data["format_version"] = True
        invalid.append(data)
        data = copy.deepcopy(original)
        data["unexpected"] = "field"
        invalid.append(data)
        data = copy.deepcopy(original)
        data["destination"] = str(self.root)
        invalid.append(data)
        data = copy.deepcopy(original)
        data["skills"][0]["files"][0]["path"] = "../../escape"
        invalid.append(data)
        data = copy.deepcopy(original)
        data["skills"][0]["files"][0]["size"] = False
        invalid.append(data)
        data = copy.deepcopy(original)
        data["skills"].append(copy.deepcopy(data["skills"][0]))
        invalid.append(data)
        for number, data in enumerate(invalid):
            with self.subTest(case=number):
                self.manifest.write_text(json.dumps(data))
                self.assertEqual(self.verify(expected=2)["status"], "BLOCKED")

    def test_duplicate_json_keys_are_rejected(self):
        self.install("controlled-github")
        data = self.manifest.read_text()
        self.manifest.write_text('{"format_version": 1,' + data.lstrip()[1:])
        self.assertEqual(self.verify(expected=2)["status"], "BLOCKED")

    def test_system_temp_directory_is_not_needed(self):
        env = self.env.copy()
        env.update(TMPDIR=str(self.root / "not-present"), TMP=str(self.root / "not-present"), TEMP=str(self.root / "not-present"))
        runner = textwrap.dedent("""\
            import os, runpy, sys, tempfile
            denied = []
            def audit(event, arguments):
                blocked = event in ('tempfile.mkstemp', 'tempfile.mkdtemp')
                if event in ('open', 'os.mkdir', 'os.listdir', 'os.scandir',
                             'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink'):
                    for value in arguments:
                        if isinstance(value, (str, bytes)):
                            path = os.path.abspath(os.fsdecode(value))
                            if any(path == root or path.startswith(root + '/')
                                   for root in ('/tmp', '/var/tmp')):
                                blocked = True
                if blocked:
                    denied.append(event)
                    raise RuntimeError('SYSTEM_TEMP_DENIED')
            sys.addaudithook(audit)
            if sys.argv[1] == '--probe':
                probes = (
                    lambda: tempfile.mkdtemp(dir=sys.argv[2]),
                    lambda: tempfile.mkstemp(dir=sys.argv[2]),
                    lambda: open('/tmp/acp-audit-probe', 'rb'),
                    lambda: open('/var/tmp/acp-audit-probe', 'rb'),
                )
                for probe in probes:
                    try:
                        probe()
                    except RuntimeError as error:
                        assert str(error) == 'SYSTEM_TEMP_DENIED'
                    else:
                        raise AssertionError('audit hook did not block the probe')
                assert len(denied) == len(probes)
                sys.exit(0)
            helper = sys.argv[1]
            sys.argv = sys.argv[1:]
            code = 0
            try:
                runpy.run_path(helper, run_name='__main__')
            except SystemExit as error:
                code = error.code
            if denied:
                raise AssertionError('helper attempted a forbidden temporary operation')
            sys.exit(code)
        """)
        command = [sys.executable, "-B", "-c", runner]
        # Negative controls prove the guard rejects both tempfile APIs and
        # system-temp file access before a real helper invocation is trusted.
        probe = subprocess.run(command + ["--probe", str(self.root)],
                               cwd=self.root, env=env, capture_output=True, timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        operations = (
            self.arguments("controlled-github"),
            ["verify", "--manifest", str(self.manifest)],
        )
        for arguments in operations:
            with self.subTest(operation=arguments[0]):
                result = subprocess.run(command + [str(HELPER), *arguments],
                                        cwd=self.root, env=env, capture_output=True,
                                        text=True, timeout=30)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(json.loads(result.stdout)["status"], "PASS")
        self.assertFalse((self.root / "not-present").exists())

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory write permission")
    def test_manifest_write_denial_means_no_skill_copy(self):
        self.work.chmod(0o555)
        self.addCleanup(self.work.chmod, 0o755)
        self.install("controlled-github", expected=2)
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.dest.exists())

    def test_dest_and_manifest_are_explicit_and_bounded(self):
        cases = [
            {"dest": self.project / "other" / "skills"},
            {"manifest": self.dest.parent / "settings.json"},
            {"manifest": self.dest / "skills-install.json"},
            {"manifest": self.dest / "controlled-github" / "skills-install.json"},
            {"manifest": self.project / ".agents" / "skills" / "skills-install.json"},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.install("controlled-github", expected=2, **values)
                self.assertFalse(self.dest.exists())

    def test_unknown_duplicate_or_mixed_selection_is_rejected(self):
        options = (
            ["--skill", "unknown-skill"],
            ["--skill", "controlled-github", "--skill", "controlled-github"],
            ["--all", "--skill", "controlled-github"],
        )
        base = self.arguments()[:-1]
        for selection in options:
            with self.subTest(selection=selection):
                self.run_cli(base + selection, expected=2)
                self.assertFalse(self.manifest.exists())
                self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
