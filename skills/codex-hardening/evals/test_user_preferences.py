"""Bounded user preferences, distinct from plugin and workspace authority."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("user_preference_harden", Path(__file__).resolve().parents[1] / "scripts" / "harden.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

PREFERENCES = '''[features]
fast_mode = true
[tui]
status_line = ["model", "context-remaining"]
status_line_use_colors = false
screen_reader_detection_done = true
session_picker_view = "dense"
resume_cwd = "current"
[tui.model_availability_nux]
fixture_model = 1
[notice]
fast_default_opt_out = false
hide_rate_limit_model_nudge = true
[notice.model_migrations]
fixture_old = "fixture_new"
'''

COEXISTENCE = PREFERENCES.replace('resume_cwd = "current"', 'resume_cwd = "session"') + '''
[plugins."fixture@fixture-market"]
enabled = true
[marketplaces.fixture-market]
source_type = "git"
source = "https://example.invalid/fixture.git"
ref = "fixture-ref"
last_revision = "fixture-revision"
last_updated = "2026-11-03T00:00:00Z"
sparse_paths = ["plugins"]
'''


class UserPreferenceTests(unittest.TestCase):
    def issues(self, config, user_policy="display-v1", kind="user"):
        return h.configuration_issues(config, kind, "preferences-v1", user_policy)

    def test_bounded_preferences_accepted_without_rewrite(self):
        config = h.parse_toml(PREFERENCES.encode())
        before = json.dumps(config, sort_keys=True)
        self.assertEqual(self.issues(config), [])
        config["features"]["fast_mode"] = False
        self.assertEqual(self.issues(config), [])
        config["features"]["fast_mode"] = True
        self.assertEqual(json.dumps(config, sort_keys=True), before)

    def test_policy_and_project_scope_are_not_widened(self):
        config = h.parse_toml(PREFERENCES.encode())
        self.assertIn("FEATURE_FLAGS_REQUIRE_REVIEW", self.issues(config, None))
        self.assertIn("UNREVIEWED_PROJECT_KEYS", self.issues(config, kind="project"))

    def test_invalid_types_bounds_and_unknown_nested_keys(self):
        for config in (
            {"features": {"fast_mode": "true"}}, {"features": []},
            {"tui": {"status_line": "model"}}, {"tui": {"status_line": ["x"] * 33}},
            {"tui": {"status_line_use_colors": 1}},
            {"tui": {"screen_reader_detection_done": "true"}},
            {"tui": {"session_picker_view": "arbitrary"}},
            {"tui": {"model_availability_nux": {"fixture": True}}},
            {"tui": {"model_availability_nux": {"fixture": 2**32}}},
            {"notice": {"model_migrations": {"fixture": 4}}},
            {"notice": {"model_migrations": {str(i): "x" for i in range(129)}}},
            {"notice": {"fast_default_opt_out": 0}},
        ):
            with self.subTest(config=config):
                self.assertIn("INVALID_USER_PREFERENCE", self.issues(config))
        for config in ({"features": {"network_proxy": False}},
                       {"tui": {"future_option": True}},
                       {"notice": {"future_option": False}}):
            self.assertTrue(self.issues(config))

    def test_authority_changing_settings_still_require_review(self):
        for config, reason in (
            ({"plugins": {"private-plugin": {"mcp_servers": {}}}}, "PLUGIN_CONFIGURATION_REQUIRES_REVIEW"),
            ({"marketplaces": {"fixture": {"future_policy": True}}}, "MARKETPLACE_CONFIGURATION_REQUIRES_REVIEW"),
            ({"permissions": {}}, "PERMISSION_MODEL_CONFLICT"),
            ({"notice": {"hide_full_access_warning": True}}, "UNREVIEWED_NOTICE_KEYS"),
            ({"features": {"fast_mode": True, "hooks": True}}, "FEATURE_FLAGS_REQUIRE_REVIEW"),
        ):
            self.assertIn(reason, self.issues(config))

    def test_metadata_and_resume_are_preserved_not_certified(self):
        config = h.parse_toml(COEXISTENCE.encode())
        before = json.dumps(config, sort_keys=True)
        self.assertEqual(self.issues(config), [])
        self.assertEqual(json.dumps(config, sort_keys=True), before)
        self.assertEqual(self.issues({"plugins": {}, "marketplaces": {}}), [])
        self.assertTrue(self.issues(config, None))
        self.assertTrue(self.issues(config, kind="project"))

    def test_extension_metadata_is_bounded_and_typed(self):
        for config in (
            {"plugins": []}, {"plugins": {"fixture": {"enabled": 1}}},
            {"plugins": {"fixture": "enabled"}},
            {"plugins": {str(i): {} for i in range(129)}},
            {"marketplaces": {"fixture": {"source_type": "unknown"}}},
            {"marketplaces": {"fixture": {"source": []}}},
            {"marketplaces": {"fixture": {"source": "x" * 4097}}},
            {"marketplaces": {"fixture": {"sparse_paths": [1]}}},
            {"marketplaces": {"fixture": {"sparse_paths": ["x"] * 129}}},
            {"plugins": {"\nprivate": {}}},
        ):
            with self.subTest(config=config):
                self.assertIn("INVALID_EXTENSION_METADATA", self.issues(config))

    def test_coexistence_lifecycle_drift_and_recovery(self):
        # Runtime boundaries mocked here; native fixture below tests enforcement.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home, work = root / "home", root / "work"
            home.mkdir()
            work.mkdir()
            config = home / "config.toml"
            config.write_text(COEXISTENCE)
            manager = h.Manager(home, work, Path(sys.executable).resolve(), "development")
            recipe = {"id": "fixture", "protections": "default-v1",
                      "config_policy": "preferences-v1", "user_preferences": "display-v1"}
            with patch.object(h, "detect", return_value=({}, "0.166.0", recipe)), \
                 patch.object(manager, "layers", return_value=[(config, "user")]), \
                 patch.object(manager, "check_candidate", return_value={"status": "PASS"}):
                plan = manager.plan()
                self.assertEqual(plan["status"], "READY")
                self.assertEqual(plan["observations"]["plugins"], "configured")
                self.assertIn("PLUGINS_NOT_VERIFIED", plan["scope_warnings"])
                self.assertEqual(plan["verification_scope"], "selected-workspace-and-profile; new-session-only")
                for private in ("fixture@", "example.invalid", "fixture-ref"):
                    self.assertNotIn(private, json.dumps(plan))
                config.write_text(COEXISTENCE.replace("enabled = true", "enabled = false"))
                with self.assertRaisesRegex(h.Stop, "STALE_PLAN"):
                    manager.apply(plan["plan_id"])
                self.assertFalse(manager.target.exists())
                config.write_text(COEXISTENCE)
                result = manager.apply(manager.plan()["plan_id"])
                self.assertEqual(result["status"], "APPLIED")
                self.assertIn("PLUGINS_NOT_VERIFIED", result["scope_warnings"])
                self.assertEqual(manager.verify()["other_surfaces"], "NOT_VERIFIED")
                installed = manager.target.read_text()
                manager.target.write_text(installed + "# user edit\n")
                with self.assertRaises(h.Stop):
                    manager.rollback()
                self.assertTrue(manager.target.read_text().endswith("# user edit\n"))
                manager.target.write_text(installed)
                self.assertEqual(manager.rollback()["status"], "RESTORED")
                self.assertFalse(manager.target.exists())
                self.assertEqual(config.read_text(), COEXISTENCE)


@unittest.skipUnless(os.environ.get("CODEX_HARDENING_BINARY"), "native CLI integration is opt-in")
class NativeUserPreferenceTests(unittest.TestCase):
    def test_preserved_user_preferences_with_real_profile_and_negative_control(self):
        binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        identity, version, recipe = h.detect(binary)
        self.assertEqual(version, os.environ.get("CODEX_HARDENING_EXPECTED_VERSION"))
        self.assertEqual(recipe.get("user_preferences"), "display-v1")
        with tempfile.TemporaryDirectory(prefix="acp-user-preferences-") as temporary:
            root = Path(temporary)
            home, work = root / "home", root / "work"
            home.mkdir()
            work.mkdir()
            config = home / "config.toml"
            config.write_text(COEXISTENCE)
            manager = h.Manager(home, work, binary, "development")
            plan = manager.plan()
            self.assertEqual(plan["status"], "READY", plan["issues"])
            self.assertEqual(manager.apply(plan["plan_id"])["status"], "APPLIED")
            self.assertEqual(manager.verify()["status"], "PASS")
            self.assertEqual(config.read_text(), COEXISTENCE)
            command = [str(binary), "sandbox", "--profile", "acp-development",
                       "--permission-profile", "acp-development", "--cd", str(work),
                       "--", sys.executable, "-I", "-B", "-c", "print('FIXTURE')"]
            # Native parsing must reject invalid values, not silently ignore this file.
            for bad in ('[features]\nfast_mode = "invalid"\n',
                        '[tui]\nstatus_line_use_colors = "invalid"\n',
                        '[notice]\nfast_default_opt_out = "invalid"\n',
                        '[plugins."fixture@fixture-market"]\nenabled = "invalid"\n',
                        '[marketplaces.fixture-market]\nsource_type = "invalid"\n'):
                config.write_text(bad)
                rc, out, _ = h.run(command, home, work)
                self.assertNotEqual(rc, 0)
                self.assertNotIn(b"FIXTURE", out)
            config.write_text(COEXISTENCE + '\n[plugins.private_fixture.mcp_servers]\n')
            self.assertIn("PLUGIN_CONFIGURATION_REQUIRES_REVIEW", manager.plan()["issues"])
            self.assertIsNone(manager.plan()["plan_id"])
            config.write_text(COEXISTENCE)
            self.assertEqual(manager.uninstall()["status"], "UNINSTALLED")
            self.assertFalse(manager.target.exists())
            self.assertEqual(manager.rollback()["status"], "RESTORED")
            self.assertEqual(manager.verify()["status"], "PASS")
            self.assertEqual(config.read_text(), COEXISTENCE)
        self.assertEqual(h.executable_identity(binary), identity)
