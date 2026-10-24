"""Isolated acceptance and regression tests; never use the real Codex home."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harden.py"
spec = importlib.util.spec_from_file_location("harden", SCRIPT)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class IntentTests(unittest.TestCase):
    def test_development_intent(self):
        config = tomllib.loads(h.render_profile("development"))
        self.assertEqual(config.get("default_permissions"), "acp-development")
        self.assertEqual(config.get("approval_policy"), "on-request")
        self.assertEqual(config.get("approvals_reviewer"), "user")
        permission = config["permissions"]["acp-development"]
        self.assertFalse(permission["network"]["enabled"])
        self.assertEqual(permission["extends"], ":read-only")
        self.assertEqual(permission["filesystem"][":workspace_roots"]["."], "write")
        self.assertEqual(permission["filesystem"][":workspace_roots"][".git"], "read")

    def test_review_intent(self):
        config = tomllib.loads(h.render_profile("review"))
        self.assertEqual(config["permissions"]["acp-review"]["extends"], ":read-only")
        self.assertEqual(config["permissions"]["acp-review"]["filesystem"][":workspace_roots"]["."], "read")
        self.assertNotIn("history", config)
        self.assertNotIn("mcp_servers", config)

    def test_unknown_mode(self):
        with self.assertRaisesRegex(h.Stop, "UNKNOWN_MODE"):
            h.render_profile("full-access")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.work = self.root / "workspace"
        self.home.mkdir()
        self.work.mkdir()
        self.manager = h.Manager(self.home, self.work, Path(sys.executable).resolve(), "development")
        self.detect = patch.object(h, "detect", return_value=(
            {"path": "fixture", "sha256": "a" * 64}, "0.163.0", {"id": "fixture"}))
        self.detect.start()
        self.addCleanup(self.detect.stop)
        # Isolate tests from the host's managed and ancestor configuration.
        self.layers = patch.object(self.manager, "layers", return_value=[(self.home / "config.toml", "user")])
        self.layers.start()
        self.addCleanup(self.layers.stop)
        self.probe = patch.object(h, "probe", return_value={"status": "PASS", "checks": {"fixture": "PASS"}})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def apply(self):
        return self.manager.apply(self.manager.plan()["plan_id"])

    def test_inspect_and_plan_do_not_write(self):
        self.assertEqual(self.manager.inspect()["status"], "READY")
        self.assertEqual(self.manager.plan()["status"], "READY")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unknown_version_can_inspect_but_not_apply(self):
        with patch.object(h, "detect", return_value=({}, "99.0.0", None)):
            result = self.manager.plan()
            self.assertIn("UNSUPPORTED_VERSION_OR_PLATFORM", result["issues"])
            with self.assertRaisesRegex(h.Stop, "PLAN_BLOCKED"):
                self.manager.apply(result["plan_id"])
        self.assertFalse(self.manager.target.exists())

    def test_apply_verify_idempotence_uninstall_cleanup(self):
        config = b'model = "test-model"\n'
        (self.home / "config.toml").write_bytes(config)
        self.assertEqual(self.apply()["status"], "APPLIED")
        self.assertEqual(self.manager.verify()["status"], "PASS")
        self.assertEqual(self.apply()["status"], "UNCHANGED")
        self.assertEqual((self.home / "config.toml").read_bytes(), config)
        self.assertEqual(self.manager.target.stat().st_mode & 0o777, 0o600)
        self.manager.uninstall()
        self.assertFalse(self.manager.target.exists())
        self.assertEqual(self.manager.uninstall()["status"], "UNCHANGED")
        self.assertEqual(self.manager.cleanup()["eligible_records"], 1)
        self.assertTrue(self.manager.state_path.exists())
        self.manager.cleanup(True)
        self.assertFalse(self.manager.state_path.exists())
        self.assertTrue((self.manager.directory / "lock").exists())

    def test_rollback_preserves_original_absence_and_can_restore(self):
        self.apply()
        self.manager.rollback()
        self.assertFalse(self.manager.target.exists())
        self.manager.rollback()
        self.assertEqual(self.manager.target.read_text(), h.render_profile("development"))

    def test_plan_stale_after_config_change(self):
        plan = self.manager.plan()
        (self.home / "config.toml").write_text('model = "changed"')
        with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
            self.manager.apply(plan["plan_id"])
        self.assertFalse(self.manager.target.exists())

    def test_plan_stale_after_binary_change(self):
        plan = self.manager.plan()
        with patch.object(h, "detect", return_value=({"sha256": "b" * 64}, "0.163.0", {"id": "fixture"})):
            with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
                self.manager.apply(plan["plan_id"])

    def test_candidate_failure_does_not_install(self):
        with patch.object(h, "probe", return_value={"status": "NOT_VERIFIED"}):
            self.assertEqual(self.apply()["status"], "NOT_VERIFIED")
        self.assertFalse(self.manager.target.exists())

    def test_config_drift_during_probes(self):
        def modify(*args):
            (self.home / "config.toml").write_text('model = "changed"')
            return {"status": "PASS"}
        with patch.object(h, "probe", side_effect=modify):
            with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
                self.apply()
        self.assertFalse(self.manager.target.exists())

    def test_verify_never_uses_old_pass(self):
        self.apply()
        with patch.object(h, "probe", return_value={"status": "FAIL"}):
            self.assertEqual(self.manager.verify()["status"], "FAIL")

    def test_changed_managed_profile_is_preserved(self):
        self.apply()
        self.manager.target.write_text("# manual edit")
        self.assertIn("MANAGED_PROFILE_DRIFT", self.manager.inspect()["issues"])
        for operation in (self.manager.uninstall, self.manager.rollback):
            with self.assertRaisesRegex(h.Stop, "MANAGED_PROFILE_DRIFT"):
                operation()
        self.assertEqual(self.manager.cleanup(True)["removed_records"], 0)
        self.assertEqual(self.manager.target.read_text(), "# manual edit")

    def test_existing_unmanaged_profile_is_not_adopted(self):
        self.manager.target.write_text(h.render_profile("development"))
        with self.assertRaisesRegex(h.Stop, "PLAN_BLOCKED"):
            self.apply()

    def test_symlink_target_and_parent(self):
        victim = self.root / "victim"
        victim.write_text("unchanged")
        self.manager.target.symlink_to(victim)
        with self.assertRaisesRegex(h.Stop, "SYMLINK_PATH"):
            self.manager.inspect()
        self.assertEqual(victim.read_text(), "unchanged")
        alias = self.root / "alias"
        alias.symlink_to(self.home, target_is_directory=True)
        with self.assertRaisesRegex(h.Stop, "SYMLINK_PATH"):
            h.Manager(alias, self.work, sys.executable, "review")

    def test_hardlinks_and_oversized_input(self):
        source = self.root / "source"
        source.write_text("test")
        target = self.home / "config.toml"
        os.link(source, target)
        with self.assertRaisesRegex(h.Stop, "UNSUPPORTED_FILE"):
            self.manager.inspect()
        target.unlink()
        target.write_bytes(b" " * (h.MAX_FILE + 1))
        with self.assertRaisesRegex(h.Stop, "UNSUPPORTED_FILE"):
            self.manager.inspect()

    def test_unknown_keys_permission_model_and_features_block(self):
        for text, reason in (
            ('new_policy = true', "UNREVIEWED_CONFIG_KEYS"),
            ('default_permissions = ":workspace"', "PERMISSION_MODEL_CONFLICT"),
            ('[features]\nnew_feature = true', "FEATURE_FLAGS_REQUIRE_REVIEW"),
        ):
            with self.subTest(reason=reason):
                (self.home / "config.toml").write_text(text)
                self.assertIn(reason, self.manager.inspect()["issues"])

    def test_opaque_layers_require_review(self):
        for kind in ("managed", "project", "hooks", "rules"):
            path = self.root / "opaque"
            path.write_text("sensitive synthetic data")
            with patch.object(self.manager, "layers", return_value=[(path, kind)]):
                self.assertIn("REVIEW_REQUIRED_" + kind.upper(), self.manager.inspect()["issues"])

    def test_redaction(self):
        secret = "synthetic-" + "sensitive-value"
        (self.home / "config.toml").write_text(
            f'web_search = "{secret}"\n[mcp_servers.private]\nenv = {{VALUE = "{secret}"}}')
        output = json.dumps(self.manager.plan())
        self.assertNotIn(secret, output)
        self.assertNotIn("private", output)
        self.assertNotIn(str(self.home), output)
        self.assertEqual(self.manager.inspect()["observations"]["mcp_servers"], "configured")

    def test_malformed_toml_is_sanitized(self):
        (self.home / "config.toml").write_text('malformed = "synthetic-sensitive')
        with self.assertRaisesRegex(h.Stop, "^INVALID_TOML$"):
            self.manager.inspect()

    def test_lock_excludes_concurrent_writer(self):
        with self.manager.locked():
            with self.assertRaisesRegex(h.Stop, "BUSY"):
                self.manager.uninstall()

    def test_interrupted_write_recovers(self):
        original_atomic = self.manager.atomic
        def interrupt(path, data):
            if path == self.manager.state_path:
                raise OSError("simulated crash")
            original_atomic(path, data)
        with patch.object(self.manager, "atomic", side_effect=interrupt):
            with self.assertRaises(OSError):
                self.apply()
        self.assertTrue(self.manager.target.exists())
        self.assertTrue(self.manager.journal.exists())
        self.assertIn("INTERRUPTED_TRANSACTION", self.manager.inspect()["issues"])
        self.assertEqual(self.manager.rollback()["status"], "RECOVERED")
        self.assertFalse(self.manager.target.exists())
        self.assertFalse(self.manager.journal.exists())

    def test_cleanup_preserves_unknown_and_active_state(self):
        self.apply()
        unknown = self.manager.directory / "unknown"
        unknown.write_text("keep")
        self.assertEqual(self.manager.cleanup(True)["removed_records"], 0)
        self.assertTrue(self.manager.state_path.exists())
        self.assertEqual(unknown.read_text(), "keep")

    def test_settings_observations_are_allowlisted(self):
        (self.home / "config.toml").write_text(
            'approval_policy = "never"\napprovals_reviewer = "auto_review"\n'
            'allow_login_shell = true\n[history]\npersistence = "none"\n'
            '[shell_environment_policy]\ninherit = "all"\n')
        observed = self.manager.inspect()["observations"]
        self.assertEqual(observed["approval_policy"], "never")
        self.assertEqual(observed["approvals_reviewer"], "auto_review")
        self.assertTrue(observed["allow_login_shell"])
        self.assertEqual(observed["history_persistence"], "none")
        self.assertEqual(observed["shell_environment_inherit"], "all")

    def test_recovery_refuses_changed_target(self):
        original_atomic = self.manager.atomic
        def interrupt(path, data):
            if path == self.manager.state_path:
                raise OSError("simulated crash")
            original_atomic(path, data)
        with patch.object(self.manager, "atomic", side_effect=interrupt):
            with self.assertRaises(OSError):
                self.apply()
        self.manager.target.write_text("# user changed after crash")
        with self.assertRaisesRegex(h.Stop, "RECOVERY_DRIFT"):
            self.manager.rollback()
        self.assertTrue(self.manager.journal.exists())

    def test_failure_before_profile_write_recovers(self):
        with patch.object(self.manager, "replace_target", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                self.apply()
        self.assertFalse(self.manager.target.exists())
        self.assertEqual(self.manager.rollback()["status"], "RECOVERED")

    def test_read_only_inspect_does_not_create_state_lock(self):
        self.manager.cleanup()
        self.assertFalse(self.manager.directory.exists())

    def test_malformed_state_is_not_overwritten(self):
        self.apply()
        self.manager.state_path.write_text('{"schema":999}')
        with self.assertRaisesRegex(h.Stop, "STATE_SCHEMA_UNSUPPORTED"):
            self.manager.uninstall()
        self.assertTrue(self.manager.target.exists())

    def test_untrusted_management_directory(self):
        self.home.chmod(0o777)
        with self.assertRaisesRegex(h.Stop, "UNSAFE_MANAGEMENT_HOME"):
            self.apply()
        self.assertFalse(self.manager.target.exists())


class ProcessTests(unittest.TestCase):
    def test_output_and_time_limits(self):
        with tempfile.TemporaryDirectory() as home:
            with self.assertRaisesRegex(h.Stop, "PROCESS_OUTPUT_LIMIT"):
                h.run([sys.executable, "-I", "-c", "print('x' * 200000)"], home, home)
            with self.assertRaisesRegex(h.Stop, "PROCESS_TIMEOUT"):
                h.run([sys.executable, "-I", "-c", "import time; time.sleep(5)"], home, home, .1)

    def test_environment_is_not_inherited(self):
        with patch.dict(os.environ, {"SYNTHETIC_SECRET": "test", "LD_PRELOAD": "test"}):
            self.assertEqual(set(h.clean_env("/test")), {"PATH", "HOME", "CODEX_HOME", "LANG"})

    def test_missing_capability_is_not_supported(self):
        with patch.object(h, "executable_identity", return_value={}), patch.object(
                h, "run", side_effect=[(0, b"codex-cli 0.163.0\n", b""), (0, b"old CLI", b"")]):
            with self.assertRaisesRegex(h.Stop, "CLI_CAPABILITY_MISMATCH"):
                h.detect(Path("/fixture"))

    def test_sandbox_start_failure_is_not_denial(self):
        def fake(argv, *args, **kwargs):
            if "sandbox" in argv:
                return 1, b"", b"startup failed"
            # Positive-control writes must actually create the file.
            return original(argv, *args, **kwargs)
        original = h.run
        with patch.object(h, "run", side_effect=fake):
            result = h.probe(Path("/fixture"), "development")
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_ignored_sandbox_is_a_failure(self):
        original = h.run
        def fake(argv, *args, **kwargs):
            if "sandbox" in argv:
                argv = argv[argv.index("--") + 1:]
            return original(argv, *args, **kwargs)
        with patch.object(h, "run", side_effect=fake):
            result = h.probe(Path("/fixture"), "development")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"]["outside_write"], "FAIL")
        self.assertEqual(result["checks"]["command_network"], "FAIL")


@unittest.skipUnless(os.environ.get("CODEX_HARDENING_BINARY"), "native CLI integration is opt-in")
class RealCliTests(unittest.TestCase):
    def test_native_recipe_and_both_profiles(self):
        binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        _, version, recipe = h.detect(binary)
        self.assertEqual(version, "0.163.0")
        self.assertIsNotNone(recipe)
        for mode in h.MODES:
            with self.subTest(mode=mode):
                self.assertEqual(h.probe(binary, mode)["status"], "PASS")

    def test_real_lifecycle_in_temporary_home(self):
        binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        with tempfile.TemporaryDirectory(prefix="codex-hardening-lifecycle-") as temporary:
            root = Path(temporary)
            home, work = root / "home", root / "workspace"
            home.mkdir()
            work.mkdir()
            (home / "config.toml").write_text('model = "fixture-only"\n')
            for mode in h.MODES:
                with self.subTest(mode=mode):
                    manager = h.Manager(home, work, binary, mode)
                    plan = manager.plan()
                    self.assertEqual(plan["status"], "READY", plan["issues"])
                    self.assertEqual(manager.apply(plan["plan_id"])["status"], "APPLIED")
                    self.assertEqual(manager.verify()["status"], "PASS")
                    manager.uninstall()
                    manager.rollback()
                    self.assertEqual(manager.verify()["status"], "PASS")
                    manager.uninstall()
                    self.assertEqual(manager.cleanup(True)["removed_records"], 1)
            self.assertEqual((home / "config.toml").read_text(), 'model = "fixture-only"\n')


if __name__ == "__main__":
    unittest.main()
