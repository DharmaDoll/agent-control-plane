"""Isolated acceptance and regression tests; never use the real Codex home."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
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
            {"path": "fixture", "sha256": "a" * 64}, "0.163.0", {"id": "fixture", "protections": "default-v1"}))
        self.detect.start()
        self.addCleanup(self.detect.stop)
        # Isolate tests from the host's managed and ancestor configuration.
        self.layers = patch.object(self.manager, "layers", return_value=[(self.home / "config.toml", "user")])
        self.layers.start()
        self.addCleanup(self.layers.stop)
        self.probe = patch.object(h, "probe", return_value={"status": "PASS", "checks": {"fixture": "PASS"}})
        self.probe.start()
        self.addCleanup(self.probe.stop)
        credential_probe = patch.object(h, "credential_probe", return_value={"status": "PASS"})
        credential_probe.start()
        self.addCleanup(credential_probe.stop)

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
        self.assertEqual(self.manager.target.read_text(), self.manager.candidate())

    def test_plan_stale_after_config_change(self):
        plan = self.manager.plan()
        (self.home / "config.toml").write_text('model = "changed"')
        with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
            self.manager.apply(plan["plan_id"])
        self.assertFalse(self.manager.target.exists())

    def test_plan_stale_after_binary_change(self):
        plan = self.manager.plan()
        with patch.object(h, "detect", return_value=({"sha256": "b" * 64}, "0.163.0", {"id": "fixture", "protections": "default-v1"})):
            with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
                self.manager.apply(plan["plan_id"])

    def test_candidate_failure_does_not_install(self):
        with patch.object(h, "probe", return_value={"status": "NOT_VERIFIED"}):
            self.assertEqual(self.apply()["status"], "NOT_VERIFIED")
        self.assertFalse(self.manager.target.exists())

    def test_config_drift_during_probes(self):
        def modify(*args, **kwargs):
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
        self.manager.target.write_text(self.manager.candidate())
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

    def test_blocked_plan_is_reference_only_with_safe_review_details(self):
        original = ('"synthetic-private-key-name" = "synthetic-private-value"\n'
                    '[plugins.private_plugin]\nenabled = true\n'
                    '[tui]\nnotifications = true\n'
                    '[features]\nfast_mode = true\nprivate_feature = true\n')
        config = self.home / "config.toml"
        config.write_text(original)
        report = self.manager.plan()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["applicable"])
        self.assertIsNone(report["plan_id"])
        self.assertEqual(report["candidate_status"], "REFERENCE_ONLY")
        details = report["configuration"][0]["review_details"]
        self.assertEqual(details["recognized_unreviewed_keys"], ["plugins", "tui"])
        self.assertEqual(details["unknown_key_count"], 1)
        self.assertEqual(details["recognized_features"], ["fast_mode"])
        self.assertEqual(details["unknown_feature_count"], 1)
        self.assertTrue(report["next_steps"])
        output = json.dumps(report)
        for private in ("synthetic-private", "private_plugin", "private_feature"):
            self.assertNotIn(private, output)
        self.assertEqual(config.read_text(), original)
        self.assertFalse(self.manager.target.exists())
        self.assertFalse(self.manager.directory.exists())

    def test_ready_plan_remains_applicable(self):
        report = self.manager.plan()
        self.assertTrue(report["applicable"])
        self.assertEqual(report["candidate_status"], "REQUIRES_APPROVAL")
        self.assertEqual(len(report["plan_id"]), 64)

    def test_invalid_feature_shape_has_no_raw_diagnostics(self):
        (self.home / "config.toml").write_text('features = "private-feature-value"')
        report = self.manager.plan()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["configuration"][0]["review_details"]["feature_shape"], "INVALID")
        self.assertNotIn("private-feature-value", json.dumps(report))

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


class ConfigFixture(unittest.TestCase):
    """Use the real collector/parser with files under an isolated HOME layout."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-hardening-layers-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user_home = self.root / "user"
        self.home = self.user_home / ".codex"
        self.work = self.user_home / "projects" / "app"
        self.home.mkdir(parents=True)
        self.work.mkdir(parents=True)
        self.config = self.home / "config.toml"
        self.config.write_text('model = "fixture-only"\n')
        self.manager = h.Manager(self.home, self.work, Path(sys.executable).resolve(), "development")
        detection = patch.object(h, "detect", return_value=(
            {"path": "fixture", "sha256": "a" * 64}, "0.163.0", {"id": "fixture", "protections": "default-v1"}))
        detection.start()
        self.addCleanup(detection.stop)
        original_read = h.read_file

        def read_fixture(path, limit=h.MAX_FILE):
            # Hide host/system config contents, not the layer collector or the
            # parser. Real CLI tests below exercise the unmocked lifecycle.
            path = Path(path)
            if path.is_relative_to(self.root) or path.is_relative_to(h.ROOT):
                return original_read(path, limit)
            return None

        reader = patch.object(h, "read_file", side_effect=read_fixture)
        self.reader = reader.start()
        self.addCleanup(reader.stop)


class ConfigLayerTests(ConfigFixture):
    def test_normal_home_user_config_is_read_once_without_project_blocker(self):
        result = self.manager.inspect()
        self.assertEqual(result["status"], "READY", result["issues"])
        self.assertEqual([kind for path, kind in self.manager.layers() if path == self.config], ["user"])
        self.assertEqual(sum(call.args[0] == self.config for call in self.reader.call_args_list), 1)
        self.assertFalse(self.manager.directory.exists())

    def test_custom_home_and_sibling_workspace(self):
        custom_home = self.root / "custom-codex"
        custom_home.mkdir()
        (custom_home / "config.toml").write_text('model = "fixture-only"\n')
        sibling = self.root / "sibling-workspace"
        sibling.mkdir()
        manager = h.Manager(custom_home, sibling, sys.executable, "review")
        result = manager.inspect()
        self.assertEqual(result["status"], "READY", result["issues"])
        # A different .codex/config.toml in the workspace's ancestry is still
        # a project candidate, even when a custom CODEX_HOME is selected.
        manager = h.Manager(custom_home, self.work, sys.executable, "review")
        self.assertIn((self.config, "project"), manager.layers())
        self.assertEqual(manager.inspect()["issues"], ["REVIEW_REQUIRED_PROJECT"])

    def test_workspace_equal_to_home_parent(self):
        manager = h.Manager(self.home, self.user_home, sys.executable, "review")
        result = manager.inspect()
        self.assertEqual(result["issues"], ["WORKSPACE_CONTAINS_USER_HOME"])
        self.assertNotIn("REVIEW_REQUIRED_PROJECT", result["issues"])

    def test_distinct_project_configs_are_not_skipped(self):
        for parent in (self.user_home / "projects", self.work):
            config = parent / ".codex" / "config.toml"
            config.parent.mkdir()
            config.write_text('model = "project-fixture"\n')
            self.assertIn((config, "project"), self.manager.layers())
        self.assertEqual(self.manager.inspect()["issues"], ["REVIEW_REQUIRED_PROJECT"])

    def test_user_permission_conflict_is_still_blocked(self):
        self.config.write_text('sandbox_mode = "workspace-write"\n')
        self.assertEqual(self.manager.inspect()["issues"], ["PERMISSION_MODEL_CONFLICT"])

    def test_overlapping_hooks_and_rules_still_require_review(self):
        hooks = self.home / "hooks.json"
        hooks.write_text("{}")
        rules = self.home / "rules"
        rules.mkdir()
        rule = rules / "fixture.rules"
        rule.write_text("# inert fixture")
        layers = self.manager.layers()
        self.assertEqual(layers.count((hooks, "hooks")), 1)
        self.assertEqual(layers.count((rule, "rules")), 1)
        self.assertEqual(self.manager.inspect()["issues"], ["REVIEW_REQUIRED_HOOKS", "REVIEW_REQUIRED_RULES"])

    def test_managed_role_is_not_hidden_by_selected_home(self):
        # Structural-only check: no /etc file is read or written by this test.
        self.manager.home = Path("/etc/codex")
        self.assertIn((Path("/etc/codex/config.toml"), "managed"), self.manager.layers())

    def test_aliases_are_rejected_not_deduplicated(self):
        project_dir = self.work / ".codex"
        project_dir.mkdir()
        project = project_dir / "config.toml"
        project.symlink_to(self.config)
        with self.assertRaisesRegex(h.Stop, "SYMLINK_PATH"):
            self.manager.inspect()
        project.unlink()
        os.link(self.config, project)
        with self.assertRaisesRegex(h.Stop, "UNSUPPORTED_FILE"):
            self.manager.inspect()

    def test_config_changes_still_invalidate_plan(self):
        before = self.manager.plan()
        self.config.write_text('model = "changed-fixture"\n')
        after = self.manager.plan()
        self.assertNotEqual(before["plan_id"], after["plan_id"])
        self.assertFalse(self.manager.directory.exists())


class ConfigPreferenceTests(ConfigFixture):
    def setUp(self):
        super().setUp()
        detection = patch.object(h, "detect", return_value=(
            {"path": "fixture", "sha256": "a" * 64}, "0.164.0",
            {"id": "fixture", "config_policy": "preferences-v1", "protections": "default-v1"}))
        detection.start()
        self.addCleanup(detection.stop)
        self.project = self.work / ".codex" / "config.toml"
        self.project.parent.mkdir()

    def test_preferences_are_preserved_and_compatible(self):
        preferences = ('model = "fixture-only"\nmodel_reasoning_effort = "high"\n'
                       'model_reasoning_summary = "none"\nmodel_verbosity = "low"\n'
                       'hide_agent_reasoning = true\n')
        self.project.write_text(preferences)
        result = self.manager.plan()
        self.assertEqual(result["status"], "READY", result["issues"])
        self.assertTrue(all(layer["status"] == "COMPATIBLE" for layer in result["configuration"]))
        self.assertEqual(self.project.read_text(), preferences)
        self.assertFalse(self.manager.directory.exists())

    def test_project_policy_overrides_are_conflicts(self):
        for text in ('default_permissions = ":workspace"', 'sandbox_mode = "workspace-write"',
                     '[permissions.acp-development.network]\nenabled = true',
                     'approval_policy = "never"', 'approvals_reviewer = "auto_review"',
                     'allow_login_shell = true', '[shell_environment_policy]\ninherit = "all"'):
            with self.subTest(text=text):
                self.project.write_text(text)
                result = self.manager.plan()
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn("PROJECT_POLICY_OVERRIDE", result["issues"])
                self.assertEqual(result["configuration"][-1]["status"], "CONFLICT")
                with self.assertRaisesRegex(h.Stop, "PLAN_BLOCKED"):
                    self.manager.apply(result["plan_id"])
                self.assertFalse(self.manager.target.exists())

    def test_unknown_project_settings_are_review_required_and_redacted(self):
        self.project.write_text('unknown_private_key_name = "synthetic-sensitive"\n')
        result = self.manager.plan()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("UNREVIEWED_PROJECT_KEYS", result["issues"])
        self.assertEqual(result["configuration"][-1]["status"], "REVIEW_REQUIRED")
        output = json.dumps(result)
        for private in ("unknown_private_key_name", "synthetic-sensitive", str(self.project)):
            self.assertNotIn(private, output)

    def test_invalid_preferences_are_not_compatible(self):
        for target in (self.config, self.project):
            for text in ('model = 1', 'model_reasoning_effort = []', 'model_verbosity = "unexpected"',
                         'hide_agent_reasoning = "true"'):
                with self.subTest(layer=target.parent.name, text=text):
                    target.write_text(text)
                    result = self.manager.inspect()
                    self.assertEqual(result["status"], "BLOCKED")
                    self.assertIn("INVALID_PREFERENCE_VALUE", result["issues"])
            target.write_text('model = "fixture-only"\n')

    def test_managed_and_feature_settings_remain_review_required(self):
        (self.home / "requirements.toml").write_text("# opaque managed layer\n")
        self.project.write_text('[features]\nnetwork_proxy = true\n')
        result = self.manager.inspect()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REVIEW_REQUIRED_MANAGED", result["issues"])
        self.assertIn("UNREVIEWED_PROJECT_KEYS", result["issues"])

    def test_compatible_project_change_invalidates_plan(self):
        self.project.write_text('model = "first-fixture"\n')
        before = self.manager.plan()
        self.assertEqual(before["status"], "READY", before["issues"])
        self.project.write_text('model = "second-fixture"\n')
        with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
            self.manager.apply(before["plan_id"])


class ProcessTests(unittest.TestCase):
    def test_exact_0164_recipe_and_unknown_versions(self):
        for version, supported in (("0.164.0", True), ("0.164.1", False), ("99.0.0", False)):
            def fake(argv, *args, **kwargs):
                if "--version" in argv:
                    return 0, f"codex-cli {version}\n".encode(), b""
                return 0, b"--strict-config --profile --permission-profile --cd --rules", b""
            with self.subTest(version=version), patch.object(h, "executable_identity", return_value={}), \
                    patch.object(h, "run", side_effect=fake):
                _, observed, recipe = h.detect(Path("/fixture"))
                self.assertEqual(observed, version)
                self.assertEqual(recipe is not None, supported)

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
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        cls.identity, cls.version, cls.recipe = h.detect(cls.binary)
        expected = os.environ.get("CODEX_HARDENING_EXPECTED_VERSION", "0.163.0")
        if cls.version != expected or cls.recipe is None:
            raise RuntimeError("expected supported native CLI version required")

    @classmethod
    def tearDownClass(cls):
        if h.executable_identity(cls.binary) != cls.identity:
            raise RuntimeError("native CLI changed during integration tests")

    def test_native_recipe_and_both_profiles(self):
        binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        _, version, recipe = h.detect(binary)
        self.assertEqual(version, self.version)
        self.assertIsNotNone(recipe)
        for mode in h.MODES:
            with self.subTest(mode=mode):
                self.assertEqual(h.probe(binary, mode)["status"], "PASS")

    def test_real_lifecycle_in_temporary_home(self):
        self.check_lifecycle(normal_home=False)

    def test_real_lifecycle_in_normal_home_layout(self):
        self.check_lifecycle(normal_home=True)

    def test_protected_metadata_directories(self):
        self.check_protected_paths(separate_gitdir=False)

    def test_git_pointer_and_separate_gitdir(self):
        self.check_protected_paths(separate_gitdir=True)

    def test_trusted_project_preferences_and_override_refusal(self):
        if self.recipe.get("config_policy") != "preferences-v1":
            self.skipTest("project preference support is version-specific")
        git = shutil.which("git")
        if git is None:
            self.skipTest("Git is required for trusted project configuration")
        with tempfile.TemporaryDirectory(prefix="codex-hardening-project-") as temporary:
            root = Path(temporary)
            home, work = root / "home", root / "workspace"
            home.mkdir()
            work.mkdir()
            rc, _, _ = h.run([git, "init", "--template=", str(work)], home, root)
            self.assertEqual(rc, 0)
            (home / "config.toml").write_text(
                f'[projects.{json.dumps(str(work))}]\ntrust_level = "trusted"\n')
            project = work / ".codex" / "config.toml"
            project.parent.mkdir()
            preferences = ('model = "fixture-only"\nmodel_reasoning_effort = "high"\n'
                           'model_reasoning_summary = "none"\nmodel_verbosity = "low"\n'
                           'hide_agent_reasoning = true\n')
            project.write_text(preferences)
            manager = h.Manager(home, work, self.binary, "development")
            plan = manager.plan()
            self.assertEqual(plan["status"], "READY", plan["issues"])
            self.assertEqual(manager.apply(plan["plan_id"])["status"], "APPLIED")
            self.assertEqual(manager.verify()["status"], "PASS")
            self.assertEqual(project.read_text(), preferences)
            # Prove the native CLI actually loads this trusted project layer:
            # invalid typed preferences must fail parsing, not be ignored.
            project.write_text('model_verbosity = "invalid-fixture"\n')
            rc, _, _ = h.run([str(self.binary), "sandbox", "--profile", "acp-development",
                              "--permission-profile", "acp-development", "--cd", str(work),
                              "--", sys.executable, "-I", "-B", "-c", "print('fixture')"], home, work)
            self.assertNotEqual(rc, 0)
            project.write_text('[permissions.acp-development.network]\nenabled = true\n')
            self.assertIn("PROJECT_POLICY_OVERRIDE", manager.inspect()["issues"])
            with patch.object(h, "probe") as probe:
                with self.assertRaisesRegex(h.Stop, "VERIFY_PRECONDITION_FAILED"):
                    manager.verify()
                probe.assert_not_called()
            manager.uninstall()
            self.assertIn("enabled = true", project.read_text())

    def check_protected_paths(self, separate_gitdir):
        binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        with tempfile.TemporaryDirectory(prefix="codex-hardening-metadata-") as temporary:
            root = Path(temporary)
            home, work = root / "home", root / "workspace"
            home.mkdir()
            work.mkdir()
            if separate_gitdir:
                git = shutil.which("git")
                if git is None:
                    self.skipTest("Git is required for the separate-gitdir fixture")
                # Keep the resolved gitdir INSIDE the writable workspace: an
                # outside path would be denied even without metadata protection.
                gitdir = work / "git-storage"
                rc, _, _ = h.run([git, "init", "--template=", "--separate-git-dir",
                                   str(gitdir), str(work)], home, root)
                self.assertEqual(rc, 0, "isolated Git setup failed")
                self.assertTrue((work / ".git").is_file())
                targets = [gitdir / "probe-marker"]
            else:
                targets = []
                for name in (".git", ".agents", ".codex", ".aws"):
                    directory = work / name
                    directory.mkdir()
                    targets.append(directory / "probe-marker")
            for mode in h.MODES:
                (home / ("acp-" + mode + ".config.toml")).write_text(h.render_profile(mode))
                for target in targets:
                    with self.subTest(mode=mode, target=target.parent.name):
                        command = [sys.executable, "-I", "-B", "-c", h.PROBE_CODE, "write", str(target)]
                        rc, out, _ = h.run(command, home, work)
                        self.assertEqual((rc, out), (0, b"START\nALLOWED\n"), "positive control failed")
                        self.assertTrue(target.is_file())
                        target.unlink()
                        rc, out, _ = h.run([str(binary), "sandbox", "--profile", "acp-" + mode,
                                            "--permission-profile", "acp-" + mode,
                                            "--cd", str(work), "--", *command], home, work)
                        self.assertEqual((rc, out), (0, b"START\nDENIED\n"))
                        self.assertFalse(target.exists(), "denied operation created a file")

    def check_lifecycle(self, normal_home):
        binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        with tempfile.TemporaryDirectory(prefix="codex-hardening-lifecycle-") as temporary:
            root = Path(temporary)
            if normal_home:
                home, work = root / "user" / ".codex", root / "user" / "projects" / "app"
            else:
                home, work = root / "home", root / "workspace"
            home.mkdir(parents=True)
            work.mkdir(parents=True)
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
