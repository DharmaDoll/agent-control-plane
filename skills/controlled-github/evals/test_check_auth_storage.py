"""Synthetic credential-source metadata only; no real credentials or network."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "check_auth_storage.py"
spec = importlib.util.spec_from_file_location("check_auth_storage", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def entry(source="keyring", **changes):
    value = dict(host="github.com", login="fixture", active=True,
                 state="success", tokenSource=source)
    value.update(changes)
    return value


def payload(*entries):
    return {"hosts": {"github.com": list(entries)}}


class StorageTests(unittest.TestCase):
    def test_plaintext_sources(self):
        for source in ("oauth_token", "/fixture/.config/gh/hosts.yml",
                       "/fixture/custom directory/hosts.yml", "GH_CONFIG_DIR/hosts.yml",
                       r"C:\Users\fixture\AppData\Roaming\GitHub CLI\hosts.yml"):
            with self.subTest(source=source):
                self.assertEqual(helper.classify_source(source), "PLAINTEXT")

    def test_keyring(self):
        self.assertEqual(helper.classify_source("keyring"), "KEYRING")

    def test_environment_is_not_keyring(self):
        for source in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            with self.subTest(source=source):
                self.assertEqual(helper.classify_source(source), "ENVIRONMENT")

    def test_unknown_is_not_secure_or_plaintext(self):
        for source in ("", None, 12, [], {}, "some-keyring", "other_TOKEN", "hosts.yml.bak"):
            with self.subTest(source=source):
                self.assertEqual(helper.classify_source(source), "UNKNOWN")

    def test_authenticated_plaintext_warns_not_blocks(self):
        report = helper.assess(payload(entry("/private/hosts.yml")), "github.com", "fixture")
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["authentication"], "PASS")
        self.assertEqual(report["active_storage"], "PLAINTEXT")
        self.assertEqual(report["warnings"], ["PLAINTEXT_CREDENTIAL_STORAGE"])

    def test_authenticated_keyring_passes(self):
        report = helper.assess(payload(entry()), "github.com", "Fixture")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["active_storage"], "KEYRING")
        self.assertEqual(report["warnings"], [])

    def test_environment_and_unknown_sources_warn(self):
        for source, warning in (("GH_TOKEN", "ENVIRONMENT_STORAGE_NOT_VERIFIED"),
                                ("future-store", "CREDENTIAL_STORAGE_UNKNOWN"),
                                (None, "CREDENTIAL_STORAGE_UNKNOWN")):
            report = helper.assess(payload(entry(source)), "github.com", "fixture")
            self.assertEqual(report["status"], "WARN")
            self.assertIn(warning, report["warnings"])

    def test_inactive_plaintext_warns_even_if_its_token_is_invalid(self):
        report = helper.assess(payload(entry(), entry("/private/hosts.yml", active=False,
                                                     login="other", state="error")),
                               "github.com", "fixture")
        self.assertEqual(report["authentication"], "PASS")
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["active_storage"], "KEYRING")
        self.assertIn("PLAINTEXT_CREDENTIAL_STORAGE", report["warnings"])

    def test_env_does_not_hide_reported_saved_plaintext(self):
        report = helper.assess(payload(entry("GH_TOKEN"), entry("oauth_token", active=False)),
                               "github.com", "fixture")
        self.assertEqual(report["status"], "WARN")
        self.assertIn("PLAINTEXT_CREDENTIAL_STORAGE", report["warnings"])
        self.assertIn("ENVIRONMENT_STORAGE_NOT_VERIFIED", report["warnings"])

    def test_auth_failure_is_not_success_despite_valid_json(self):
        for state, reason in (("error", "AUTH_CHECK_FAILED"), ("timeout", "AUTH_TIMEOUT")):
            report = helper.assess(payload(entry("oauth_token", state=state)), "github.com", "fixture")
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["reason"], reason)
            self.assertEqual(report["authentication"], "FAIL")
            self.assertIn("PLAINTEXT_CREDENTIAL_STORAGE", report["warnings"])

    def test_account_mismatch_blocks_without_disclosing_identity(self):
        report = helper.assess(payload(entry(login="SYNTHETIC-PRIVATE")), "github.com", "fixture")
        self.assertEqual(report["reason"], "ACCOUNT_MISMATCH")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn("SYNTHETIC-PRIVATE", json.dumps(report))

    def test_no_auth_or_ambiguous_active_blocks(self):
        for data, reason in (({"hosts": {}}, "NOT_AUTHENTICATED"),
                             (payload(), "NOT_AUTHENTICATED"),
                             (payload(entry(active=False)), "ACTIVE_ACCOUNT_AMBIGUOUS"),
                             (payload(entry(), entry()), "ACTIVE_ACCOUNT_AMBIGUOUS")):
            report = helper.assess(data, "github.com", "fixture")
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["reason"], reason)

    def test_wrong_host_and_malformed_structure(self):
        invalid = [None, [], {}, {"hosts": []}, {"hosts": {"other.example": []}},
                   {"hosts": {"github.com": "not-a-list"}}, payload(42),
                   payload(entry(active="true")), payload(entry(active=1)),
                   payload(entry(login=None)), payload(entry(state="new-state")),
                   payload(entry(host="other.example"))]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(helper.Blocked):
                helper.assess(data, "github.com", "fixture")

    def test_account_limit(self):
        data = [entry()] + [entry(active=False)] * (helper.MAX_ACCOUNTS - 1)
        self.assertEqual(helper.assess(payload(*data), "github.com", "fixture")["status"], "PASS")
        with self.assertRaises(helper.Blocked):
            helper.assess(payload(*data, entry(active=False)), "github.com", "fixture")

    def test_raw_metadata_and_diagnostics_are_never_forwarded(self):
        marker = "SYNTHETIC-DO-NOT-DISCLOSE"
        report = helper.assess(payload(entry(f"/{marker}/hosts.yml", token=marker,
                                             error=marker, scopes=marker)), "github.com", "fixture")
        self.assertEqual(report["status"], "WARN")
        self.assertNotIn(marker, json.dumps(report))
        self.assertNotIn("hosts.yml", json.dumps(report))


class CommandTests(unittest.TestCase):
    def run_main(self, completed=None, error=None, argv=None):
        if completed is None:
            completed = subprocess.CompletedProcess([], 0, json.dumps(payload(entry())).encode())
        out, err = io.StringIO(), io.StringIO()
        with patch.object(helper.subprocess, "run", return_value=completed, side_effect=error) as run:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = helper.main(argv if argv is not None else ["--host", "github.com", "--account", "fixture"])
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("SYNTHETIC-DO-NOT-DISCLOSE", out.getvalue())
        return code, json.loads(out.getvalue()), run

    def test_exit_codes(self):
        for source, state, code in (("keyring", "success", 0), ("oauth_token", "success", 1),
                                    ("keyring", "error", 2), ("GH_TOKEN", "success", 1)):
            completed = subprocess.CompletedProcess([], 0, json.dumps(payload(entry(source, state=state))).encode())
            self.assertEqual(self.run_main(completed)[0], code)

    def test_nonzero_gh_is_not_success(self):
        completed = subprocess.CompletedProcess([], 1, json.dumps(payload(entry())).encode())
        code, report, _ = self.run_main(completed)
        self.assertEqual(code, 2)
        self.assertEqual(report["reason"], "GH_CHECK_FAILED")

    def test_invalid_output_and_limit(self):
        for raw, reason in ((b"SYNTHETIC-DO-NOT-DISCLOSE", "UNSUPPORTED_GH_OUTPUT"),
                            (b"\xff", "UNSUPPORTED_GH_OUTPUT"),
                            (b"[" * 2000, "UNSUPPORTED_GH_OUTPUT"),
                            (b"x" * (helper.MAX_OUTPUT + 1), "GH_OUTPUT_TOO_LARGE")):
            code, report, _ = self.run_main(subprocess.CompletedProcess([], 0, raw))
            self.assertEqual(code, 2)
            self.assertEqual(report["reason"], reason)
        raw = json.dumps(payload(entry())).encode()
        raw += b" " * (helper.MAX_OUTPUT - len(raw))
        self.assertEqual(self.run_main(subprocess.CompletedProcess([], 0, raw))[0], 0)

    def test_timeout_and_missing_cli_redact_exception(self):
        for error, reason in ((subprocess.TimeoutExpired("SYNTHETIC-DO-NOT-DISCLOSE", 20), "GH_TIMEOUT"),
                              (FileNotFoundError("SYNTHETIC-DO-NOT-DISCLOSE"), "CHECK_UNAVAILABLE")):
            code, report, _ = self.run_main(error=error)
            self.assertEqual(code, 2)
            self.assertEqual(report["reason"], reason)

    def test_invalid_arguments_do_not_invoke_gh(self):
        for argv in ([], ["--host", "--help"],
                     ["--host", "https://github.com", "--account", "fixture"],
                     ["--host", "github.com", "--account", "fixture;echo"],
                     ["--host", "github.com", "--account", "fixture", "--show-token"]):
            code, report, run = self.run_main(argv=argv)
            self.assertEqual(code, 2)
            self.assertEqual(report["reason"], "INVALID_ARGUMENTS")
            run.assert_not_called()

    def test_command_is_metadata_only_shell_free_and_no_auth_override(self):
        with patch.dict(os.environ, {"GH_DEBUG": "api", "GH_TOKEN": "SYNTHETIC-DO-NOT-DISCLOSE",
                                     "GH_CONFIG_DIR": "/fixture/custom", "DEBUG": "1",
                                     "GH_TELEMETRY": "log"}):
            before = dict(os.environ)
            code, _, run = self.run_main()
            self.assertEqual(dict(os.environ), before)
        self.assertEqual(code, 0)
        args, options = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(args, ["gh", "auth", "status", "--hostname", "github.com", "--json",
                                "hosts", "--jq", helper.METADATA_QUERY])
        self.assertNotIn("--active", args)  # Include reported inactive-account storage.
        self.assertNotIn("--show-token", args)
        self.assertFalse(options.get("shell", False))
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["stderr"], subprocess.DEVNULL)
        self.assertEqual(options["stdout"], subprocess.PIPE)
        self.assertEqual(options["timeout"], 20)
        self.assertNotIn("GH_DEBUG", options["env"])
        self.assertNotIn("DEBUG", options["env"])
        self.assertEqual(options["env"]["GH_TELEMETRY"], "0")
        self.assertEqual(options["env"]["GH_CONFIG_DIR"], "/fixture/custom")
        self.assertEqual(options["env"]["GH_TOKEN"], "SYNTHETIC-DO-NOT-DISCLOSE")

    @unittest.skipUnless(os.name == "posix", "Executable fixture uses a POSIX shebang")
    def test_copied_cli_with_fake_gh_preserves_files_and_redacts_stderr(self):
        with tempfile.TemporaryDirectory(prefix="gh-storage-test-") as directory:
            root = Path(directory)
            copied = root / "skill"
            shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__"))
            fake = root / "gh"
            environment = {"PATH": str(root), "GH_CONFIG_DIR": str(root / "unused-config"),
                           "PYTHONDONTWRITEBYTECODE": "1"}
            for source, state, expected in (("keyring", "success", 0), ("oauth_token", "success", 1),
                                           ("oauth_token", "error", 2)):
                data = json.dumps(payload(entry(source, state=state)))
                expected_args = ["auth", "status", "--hostname", "github.com", "--json", "hosts",
                                 "--jq", helper.METADATA_QUERY]
                fake.write_text(f"#!{sys.executable}\nimport sys\n"
                                f"assert sys.argv[1:] == {expected_args!r}\n"
                                "print('SYNTHETIC-DO-NOT-DISCLOSE', file=sys.stderr)\n"
                                f"print({data!r})\n", encoding="utf-8")
                fake.chmod(0o700)
                before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                run = subprocess.run([sys.executable, "-I", "-B", str(copied / "scripts/check_auth_storage.py"),
                                      "--host", "github.com", "--account", "fixture"],
                                     env=environment, capture_output=True, timeout=10)
                self.assertEqual(run.returncode, expected)
                self.assertEqual(run.stderr, b"")
                self.assertNotIn(b"SYNTHETIC-DO-NOT-DISCLOSE", run.stdout)
                self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
