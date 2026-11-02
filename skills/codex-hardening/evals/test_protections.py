"""Default protections use only synthetic credentials and literal rules."""
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from test_harden import h


class ProtectionTests(unittest.TestCase):
    def test_default_credentials_denied(self):
        config = tomllib.loads(h.render_profile("development"))
        fs = config["permissions"]["acp-development"]["filesystem"]
        for path in ("~/.ssh", "~/.aws", "~/.config/gcloud", "~/.azure", "~/.oci",
                     "~/.kube", "~/.docker/config.json", "~/.npmrc"):
            self.assertEqual(fs.get(path), "deny", path)

    def test_opt_out_is_narrow_and_invalid_names_fail(self):
        fs = tomllib.loads(h.render_profile("development", ["aws"]))["permissions"]["acp-development"]["filesystem"]
        self.assertNotIn("~/.aws", fs)
        self.assertEqual(fs["~/.azure"], "deny")
        with self.assertRaisesRegex(h.Stop, "UNKNOWN_PROTECTION_EXCEPTION"):
            h.render_profile("development", ["all"])
        with self.assertRaisesRegex(h.Stop, "UNKNOWN_PROTECTION_EXCEPTION"):
            h.render_rules(["aws"])

    def test_literal_rules_never_execute_code(self):
        accepted = b'prefix_rule(pattern=["git", ["status", "diff"]], decision="allow", match=["git status"])'
        self.assertEqual(h.literal_rules(accepted)[0]["decision"], "allow")
        for bad in (b'import os', b'prefix_rule(pattern=make_pattern())',
                    b'prefix_rule(pattern=["git"], decision="allow", decision="forbidden")',
                    b'prefix_rule(**{})', b'prefix_rule(pattern=[])',
                    b'prefix_rule(pattern=["x"], decision="unknown")',
                    b'prefix_rule(pattern=["x"], match="x")', b'while True: pass'):
            with self.subTest(bad=bad), self.assertRaisesRegex(h.Stop, "UNREVIEWED_RULE_SYNTAX"):
                h.literal_rules(bad)

    def test_rules_limits_and_generated_opt_out(self):
        with self.assertRaisesRegex(h.Stop, "UNREVIEWED_RULE_SYNTAX"):
            h.literal_rules(b'prefix_rule(pattern=["x"])\n' * 201)
        rules = h.literal_rules(h.render_rules(["sudo"]).encode())
        self.assertTrue(rules)
        self.assertFalse(any("sudo" in str(v) for v in rules))
        self.assertEqual(h.literal_rules(h.render_rules(["sudo", "rm"]).encode()), [])

    def test_exception_changes_plan_and_credential_files_not_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home, work = root / "codex", root / "work"
            home.mkdir(); work.mkdir()
            a = h.Manager(home, work, sys.executable, "development", user_home=root)
            b = h.Manager(home, work, sys.executable, "development", ["aws"], root)
            with patch.object(h, "detect", return_value=({}, "0.165.0", {"id": "fixture", "protections": "default-v1"})), \
                    patch.object(h.Manager, "layers", return_value=[]), \
                    patch.object(h, "read_file", wraps=h.read_file) as read:
                self.assertNotEqual(a.plan()["plan_id"], b.plan()["plan_id"])
                self.assertEqual(b.plan()["disabled_protections"], ["aws"])
                self.assertFalse(any(".aws" in str(call.args[0]) for call in read.call_args_list))
                blocked_work = root / ".aws" / "project"
                blocked_work.mkdir(parents=True)
                overlap = h.Manager(home, blocked_work, sys.executable, "development", user_home=root)
                self.assertIn("WORKSPACE_OVERLAPS_PROTECTED_PATH", overlap.inspect()["issues"])
                containing = h.Manager(home, root, sys.executable, "development", user_home=root)
                self.assertIn("WORKSPACE_CONTAINS_USER_HOME", containing.inspect()["issues"])

    def test_rules_recovery_collision_and_edited_file_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home, work = root / "home", root / "work"
            home.mkdir(); work.mkdir()
            manager = h.Manager(home, work, sys.executable, "command-rules", user_home=root)
            with patch.object(h, "detect", return_value=({}, "0.165.0", {"id": "fixture", "protections": "default-v1"})), \
                    patch.object(h.Manager, "layers", return_value=[]), \
                    patch.object(h, "rules_probe", return_value={"status": "PASS"}):
                original_atomic = manager.atomic
                def interrupt(path, data):
                    if path == manager.state_path:
                        raise OSError("fixture interruption")
                    original_atomic(path, data)
                with patch.object(manager, "atomic", side_effect=interrupt):
                    with self.assertRaises(OSError):
                        manager.apply(manager.plan()["plan_id"])
                self.assertTrue(manager.target.exists())
                self.assertEqual(manager.rollback()["status"], "RECOVERED")
                self.assertFalse(manager.target.exists())
                manager.target.write_text("# existing user file")
                self.assertIn("UNMANAGED_PROFILE_COLLISION", manager.plan()["issues"])
                manager.target.unlink()
                manager.apply(manager.plan()["plan_id"])
                manager.target.write_text("# human edit")
                with self.assertRaisesRegex(h.Stop, "MANAGED_PROFILE_DRIFT"):
                    manager.uninstall()
                self.assertEqual(manager.target.read_text(), "# human edit")

    def test_older_version_cannot_apply_unverified_protections(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = h.Manager(root, root, sys.executable, "review")
            with patch.object(h, "detect", return_value=({}, "0.164.0", {"id": "old"})), \
                    patch.object(h.Manager, "layers", return_value=[]):
                plan = manager.plan()
                self.assertIn("DEFAULT_PROTECTIONS_UNVERIFIED_VERSION", plan["issues"])
                with self.assertRaisesRegex(h.Stop, "PLAN_BLOCKED"):
                    manager.apply(plan["plan_id"])
                self.assertFalse(manager.target.exists())


@unittest.skipUnless(os.environ.get("CODEX_HARDENING_EXPECTED_VERSION") in ("0.165.0", "0.166.0")
                     and os.environ.get("CODEX_HARDENING_BINARY"), "native protections are opt-in")
class NativeProtectionTests(unittest.TestCase):
    def setUp(self):
        self.binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        identity, version, _ = h.detect(self.binary)
        self.assertEqual(version, os.environ["CODEX_HARDENING_EXPECTED_VERSION"])
        self.addCleanup(lambda: self.assertEqual(h.executable_identity(self.binary), identity))

    def test_default_read_denial_and_opt_out_both_modes(self):
        for mode in h.MODES:
            for disabled in ((), ("aws",)):
                with self.subTest(mode=mode, disabled=disabled):
                    self.assertEqual(h.credential_probe(self.binary, mode, disabled)["status"], "PASS")

    def test_explicit_user_home_not_codex_home_and_symlink_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "codex-custom"
            home.mkdir()
            work = root / "project"
            work.mkdir()
            credential = root / ".aws" / "fixture"
            credential.parent.mkdir()
            credential.write_bytes(b"inert fixture")
            alias = work / "alias"
            alias.symlink_to(credential)
            manager = h.Manager(home, work, self.binary, "development", user_home=root)
            self.assertEqual(manager.apply(manager.plan()["plan_id"])["status"], "APPLIED")
            code = ('import errno,sys\ntry:\n with open(sys.argv[1], "rb"): pass\n'
                    'except OSError as e:\n print("DENIED" if e.errno in (errno.EACCES,errno.EPERM) else "INCOMPLETE")\n'
                    'else: print("ALLOWED")\n')
            for path in (credential, alias):
                command = [sys.executable, "-I", "-B", "-c", code, str(path)]
                rc, out, _ = h.run(command, home, work)
                self.assertEqual((rc, out), (0, b"ALLOWED\n"))
                rc, out, _ = h.run([str(self.binary), "sandbox", "--profile", "acp-development",
                                    "--permission-profile", "acp-development", "--cd", str(work),
                                    "--", *command], home, work)
                self.assertEqual((rc, out), (0, b"DENIED\n"))
            self.assertEqual(manager.verify()["status"], "PASS")

    def test_native_rules_precedence_and_invalid_inline_test(self):
        candidate = h.render_rules().encode()
        allow = b'prefix_rule(pattern=["sudo"], decision="allow")\n'
        self.assertEqual(h.rules_probe(self.binary, candidate, [allow], ())["status"], "PASS")
        for argv in (["rm", "-fr", "fixture"], ["rm", "--", "fixture"], ["rm", "-f", "-r", "fixture"]):
            self.assertEqual(h.rule_decision(self.binary, [candidate], argv), "prompt")
        self.assertEqual(h.rule_decision(self.binary, [candidate], ["git", "status"]), "none")
        with self.assertRaisesRegex(h.Stop, "NATIVE_RULE_VALIDATION_FAILED"):
            h.validate_rules(self.binary, [b'prefix_rule(pattern=["git"], match=["sudo true"])'])

    def test_command_rules_lifecycle_preserves_existing_and_recovers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home, work = root / "codex", root / "work"
            home.mkdir(); work.mkdir()
            (home / "rules").mkdir()
            existing = home / "rules" / "default.rules"
            original = b'prefix_rule(pattern=["git", "status"], decision="allow")\n'
            existing.write_bytes(original)
            manager = h.Manager(home, work, self.binary, "command-rules", user_home=root)
            plan = manager.plan()
            self.assertEqual(plan["status"], "READY", plan["issues"])
            self.assertEqual(plan["installation_scope"], "codex-home-wide")
            self.assertFalse(manager.target.exists())
            self.assertEqual(manager.apply(plan["plan_id"])["status"], "APPLIED")
            self.assertEqual(manager.verify()["status"], "PASS")
            self.assertEqual(existing.read_bytes(), original)
            disabled = h.Manager(home, work, self.binary, "command-rules", ["sudo"], root)
            self.assertEqual(disabled.apply(disabled.plan()["plan_id"])["status"], "APPLIED")
            self.assertEqual(disabled.verify()["status"], "PASS")
            disabled.rollback()
            self.assertEqual(manager.verify()["status"], "PASS")
            existing.write_bytes(b'variable = "unreviewed"\n')
            self.assertIn("UNREVIEWED_RULE_SYNTAX", manager.inspect()["issues"])
            manager.uninstall()
            manager.rollback()
            manager.uninstall()
            manager.cleanup(True)
            self.assertTrue(existing.exists())
            self.assertFalse(manager.target.exists())
            self.assertFalse(manager.state_path.exists())


if __name__ == "__main__":
    unittest.main()
