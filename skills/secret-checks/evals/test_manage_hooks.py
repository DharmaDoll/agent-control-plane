"""Real Git fixtures; no network and no changes to the source checkout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
MANAGER = SKILL / "scripts/manage_hooks.py"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="secret-checks-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repository with spaces"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITLEAKS_", "PYTHON"))}
        self.env.update(HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "config"),
                        GIT_CONFIG_NOSYSTEM="1", LC_ALL="C.UTF-8")
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=self.root)
        self.git("config", "user.name", "Secret checks test")
        self.git("config", "user.email", "tests@example.invalid")

    def git(self, *args, cwd=None, ok=True, data=None):
        r = subprocess.run(["/usr/bin/git", *args], cwd=cwd or self.repo,
                           env=self.env, input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=30)
        if ok:
            self.assertEqual(r.returncode, 0, "Git operation failed; output suppressed")
        return r

    def manage(self, action, *args, ok=True, script=MANAGER):
        r = subprocess.run([sys.executable, "-B", str(script), action, "--repo", str(self.repo), *args],
                           env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout.decode())
        return r, json.loads(r.stdout)

    def stage(self, content=b"safe content\n", name="example.txt"):
        (self.repo / name).write_bytes(content)
        self.git("add", "--", name)

    def state(self):
        return json.loads((self.repo / ".git/secret-checks/state.json").read_text())

    def bundle(self, identity=None):
        return self.repo / ".git/secret-checks/bundles" / (identity or self.state()["active"])

    def test_inspect_is_read_only_and_lifecycle_is_idempotent(self):
        before = (self.repo / ".git/config").read_bytes()
        _, result = self.manage("inspect")
        self.assertEqual(result["recommendation"], "INSTALL")
        self.assertFalse((self.repo / ".git/secret-checks").exists())
        self.assertEqual(before, (self.repo / ".git/config").read_bytes())
        self.manage("install")
        state = self.state()
        self.manage("install")
        self.assertEqual(state, self.state())
        _, checked = self.manage("verify")
        self.assertEqual(checked["configuration"], "PASS")
        self.assertEqual(checked["isolated_hooks"], "PASS")
        self.manage("uninstall")
        self.assertEqual(self.git("config", "--get", "core.hooksPath", ok=False).returncode, 1)
        _, preview = self.manage("cleanup")
        self.assertEqual(len(preview["candidates"]), 1)
        self.assertTrue(self.bundle(state["active"]).exists())
        self.manage("cleanup", "--apply")
        self.assertFalse(self.bundle(state["active"]).exists())
        _, empty = self.manage("cleanup", "--apply")
        self.assertEqual(empty["removed"], [])

    def test_installed_hooks_reject_secret_and_message_without_changing_history(self):
        self.manage("install")
        self.stage()
        self.git("commit", "-q", "-m", "safe")
        self.stage(("api_" + "key=" + "x" * 16).encode())
        blocked = self.git("commit", "-q", "-m", "blocked", ok=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn(b"REJECTED", blocked.stdout + blocked.stderr)
        self.stage()
        self.git("commit", "--allow-empty", "-q", "-m", "token=" + "z" * 16, ok=False)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").stdout.strip(), b"1")

    def test_existing_hooks_and_config_are_preserved(self):
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        before = hook.read_bytes()
        r, result = self.manage("install", ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(result["reason"], "EXISTING_HOOKS")
        self.assertEqual(before, hook.read_bytes())
        hook.unlink()
        self.git("config", "core.hooksPath", "/custom/hooks")
        self.manage("install", ok=False)
        self.assertEqual(self.git("config", "--get", "core.hooksPath").stdout.strip(), b"/custom/hooks")

    def test_changed_configuration_blocks_uninstall_and_cleanup(self):
        self.manage("install")
        bundle = self.bundle()
        self.git("config", "core.hooksPath", str(self.root / "other hooks"))
        self.assertEqual(self.manage("uninstall", ok=False)[0].returncode, 2)
        self.assertEqual(self.manage("cleanup", "--apply", ok=False)[0].returncode, 2)
        self.assertTrue(bundle.exists())

    def test_unknown_or_modified_files_are_kept(self):
        self.manage("install")
        bundle = self.bundle()
        self.manage("uninstall")
        (bundle / "user-note.txt").write_text("retain me")
        _, result = self.manage("cleanup", "--apply")
        self.assertEqual(result["removed"], [])
        self.assertTrue((bundle / "user-note.txt").exists())
        (bundle / "user-note.txt").unlink()
        (bundle / "hooks/pre-commit").write_text("changed")
        _, result = self.manage("cleanup", "--apply")
        self.assertEqual(result["removed"], [])
        self.assertTrue(bundle.exists())

    def test_symlink_managed_directory_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_text("keep")
        (self.repo / ".git/secret-checks").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.manage("install", ok=False)[0].returncode, 2)
        self.assertEqual(self.manage("cleanup", "--apply", ok=False)[0].returncode, 2)
        self.assertEqual((outside / "keep").read_text(), "keep")

    def test_updates_keep_active_and_previous_then_cleanup_oldest(self):
        self.manage("install")
        first = self.state()["active"]
        copy = self.root / "copied skill"
        shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns("__pycache__"))
        scanner = copy / "scripts/scan_sensitive.py"
        scanner.write_text(scanner.read_text() + "\n# next reviewed release\n")
        self.manage("update", script=copy / "scripts/manage_hooks.py")
        second = self.state()["active"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.state()["previous"], first)
        self.manage("rollback")
        self.assertEqual(self.state()["active"], first)
        self.manage("rollback")
        self.assertEqual(self.state()["active"], second)
        _, result = self.manage("cleanup", "--apply")
        self.assertEqual(result["removed"], [])
        scanner.write_text(scanner.read_text() + "\n# third reviewed release\n")
        self.manage("update", script=copy / "scripts/manage_hooks.py")
        _, result = self.manage("cleanup", "--apply")
        self.assertEqual(result["removed"], [first])
        self.assertTrue(self.bundle(second).exists())
        self.manage("uninstall")
        self.manage("cleanup", "--apply")
        self.assertEqual(list((self.repo / ".git/secret-checks/bundles").iterdir()), [])

    def test_failed_update_leaves_active_configuration_unchanged(self):
        self.manage("install")
        before = self.git("config", "--get", "core.hooksPath").stdout
        active = self.state()["active"]
        copy = self.root / "broken skill"
        shutil.copytree(SKILL, copy)
        (copy / "scripts/scan_sensitive.py").write_text("raise SystemExit(0)\n")
        self.assertEqual(self.manage("update", script=copy / "scripts/manage_hooks.py", ok=False)[0].returncode, 2)
        self.assertEqual(self.state()["active"], active)
        self.assertEqual(self.git("config", "--get", "core.hooksPath").stdout, before)
        _, result = self.manage("cleanup", "--apply")
        self.assertEqual(len(result["removed"]), 1)

    def test_linked_worktree_is_diagnosed_and_not_silently_configured(self):
        self.stage()
        self.git("commit", "-q", "-m", "baseline")
        self.git("worktree", "add", "-q", "-b", "linked", str(self.root / "linked"))
        _, result = self.manage("inspect")
        self.assertEqual(result["recommendation"], "REVIEW_WORKTREES")
        self.assertEqual(self.manage("install", ok=False)[0].returncode, 2)

    def test_unverified_gitleaks_is_not_activated(self):
        fake = self.root / "gitleaks"
        fake.write_text("#!/bin/sh\nexit 0\n")
        r, _ = self.manage("install", "--engine", "gitleaks", "--gitleaks", str(fake), ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.git("config", "--get", "core.hooksPath", ok=False).returncode, 1)
        r, result = self.manage("install", "--gitleaks", str(fake), ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(result["reason"], "GITLEAKS_BINARY_REQUIRES_GITLEAKS_ENGINE")

    def test_verified_gitleaks_lifecycle(self):
        binary = os.environ.get("SECRET_CHECKS_GITLEAKS")
        if not binary:
            self.skipTest("SECRET_CHECKS_GITLEAKS is required for the real Gitleaks lifecycle")
        self.manage("install", "--engine", "gitleaks", "--gitleaks", binary)
        self.manage("verify")
        self.manage("update")
        self.assertEqual(self.state()["bundles"][self.state()["active"]]["engine"], "gitleaks")
        self.manage("uninstall")
        self.manage("cleanup", "--apply")

    def test_combined_requires_verified_binary_before_activation(self):
        self.manage("install")
        before = self.state()
        config = (self.repo / ".git/config").read_bytes()
        self.assertEqual(self.manage("update", "--engine", "combined", ok=False)[0].returncode, 2)
        fake = self.root / "unverified"
        fake.write_bytes(b"not a scanner")
        self.assertEqual(self.manage("update", "--engine", "combined", "--gitleaks",
                                    str(fake), ok=False)[0].returncode, 2)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.repo / ".git/config").read_bytes(), config)

    def test_combined_real_lifecycle_and_missing_child(self):
        binary = os.environ.get("SECRET_CHECKS_GITLEAKS")
        if not binary:
            self.skipTest("SECRET_CHECKS_GITLEAKS required")
        self.manage("install")
        original = self.state()["active"]
        self.manage("update", "--engine", "combined", "--gitleaks", binary)
        combined = self.state()["active"]
        self.assertEqual(self.state()["bundles"][combined]["engine"], "combined")
        self.manage("verify")
        self.manage("update")
        self.assertEqual(self.state()["active"], combined)
        self.manage("rollback")
        self.assertEqual(self.state()["active"], original)
        self.manage("rollback")
        self.assertEqual(self.state()["active"], combined)
        self.stage()
        safe = self.git("commit", "-q", "-m", "safe")
        self.assertIn(b"CHECKED engine:python", safe.stderr)
        self.assertIn(b"CHECKED engine:gitleaks", safe.stderr)
        self.stage(("api_" + "key=" + "x" * 16).encode())
        blocked = self.git("commit", "-q", "-m", "blocked", ok=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn(b"REJECTED engine:python", blocked.stderr)
        self.assertIn(b"engine:gitleaks", blocked.stderr)
        self.stage(b"a" * (2 * 1024 * 1024 + 1))
        blocked = self.git("commit", "-q", "-m", "second engine limit", ok=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn(b"CHECKED engine:python", blocked.stderr)
        self.assertIn(b"ERROR engine:gitleaks", blocked.stderr)
        self.stage()
        child = self.bundle() / "scripts/gitleaks_gate.py"
        saved = child.read_bytes()
        child.unlink()
        blocked = self.git("commit", "--allow-empty", "-q", "-m", "missing child", ok=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn(b"ERROR engine:gitleaks", blocked.stderr)
        child.write_bytes(saved)
        child.chmod(0o600)
        self.manage("uninstall")
        self.manage("cleanup", "--apply")
        self.assertEqual(list((self.repo / ".git/secret-checks/bundles").iterdir()), [])

    def test_gitleaks_to_combined_reuses_verified_binary(self):
        binary = os.environ.get("SECRET_CHECKS_GITLEAKS")
        if not binary:
            self.skipTest("SECRET_CHECKS_GITLEAKS required")
        self.manage("install", "--engine", "gitleaks", "--gitleaks", binary)
        self.manage("update", "--engine", "combined")
        self.assertEqual(self.state()["bundles"][self.state()["active"]]["engine"], "combined")
        self.manage("verify")

    def test_combined_probe_detects_one_engine_silently_passing(self):
        binary = os.environ.get("SECRET_CHECKS_GITLEAKS")
        if not binary:
            self.skipTest("SECRET_CHECKS_GITLEAKS required")
        self.manage("install")
        before = self.state()["active"]
        copy = self.root / "faulty skill"
        shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns("__pycache__"))
        (copy / "scripts/gitleaks_gate.py").write_text("raise SystemExit(0)\n")
        result, report = self.manage("update", "--engine", "combined", "--gitleaks", binary,
                                     script=copy / "scripts/manage_hooks.py", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["reason"], "PROBE_COMBINED_ENGINE_RESULT_MISSING")
        self.assertEqual(self.state()["active"], before)

    def test_cleanup_preserves_symlinks_and_untracked_bundles(self):
        self.manage("install")
        bundle = self.bundle()
        self.manage("uninstall")
        outside = self.root / "outside"
        outside.mkdir()
        keep = outside / "keep.txt"
        keep.write_text("keep")
        (bundle / "linked").symlink_to(outside, target_is_directory=True)
        (bundle.parent / "untracked").mkdir()
        self.manage("cleanup", "--apply")
        self.assertEqual(keep.read_text(), "keep")
        self.assertTrue((bundle / "linked").is_symlink())
        self.assertTrue((bundle.parent / "untracked").is_dir())

    def test_recorded_partial_bundle_can_be_cleaned(self):
        self.manage("install")
        active = self.state()["active"]
        bundle = self.bundle()
        self.manage("uninstall")
        (bundle / "hooks/pre-push").unlink()
        _, result = self.manage("cleanup", "--apply")
        self.assertEqual(result["removed"], [active])

    def test_verify_does_not_change_target_index_or_history(self):
        self.manage("install")
        self.stage()
        self.git("commit", "-q", "-m", "baseline")
        self.stage(b"uncommitted staged work\n")
        before_index = (self.repo / ".git/index").read_bytes()
        before_head = self.git("rev-parse", "HEAD").stdout
        before_config = (self.repo / ".git/config").read_bytes()
        self.manage("verify")
        self.assertEqual(before_index, (self.repo / ".git/index").read_bytes())
        self.assertEqual(before_head, self.git("rev-parse", "HEAD").stdout)
        self.assertEqual(before_config, (self.repo / ".git/config").read_bytes())

    def test_tampered_state_cannot_escape_cleanup_root(self):
        self.manage("install")
        self.manage("uninstall")
        state = self.state()
        state["bundles"][next(iter(state["bundles"]))]["files"]["../keep"] = {"sha256": "0" * 64, "mode": 0o600}
        (self.repo / ".git/secret-checks/state.json").write_text(json.dumps(state))
        self.assertEqual(self.manage("cleanup", "--apply", ok=False)[0].returncode, 2)

    def test_inspect_reports_inventory_and_refuses_known_unsupported_index(self):
        self.stage()
        _, result = self.manage("inspect")
        self.assertEqual(result["index_entries"], 1)
        self.assertEqual(result["unsupported_index_entries"], 0)
        self.assertIn("count", result["object_database"])
        (self.repo / "link").symlink_to("example.txt")
        self.git("add", "link")
        _, result = self.manage("inspect")
        self.assertEqual(result["recommendation"], "REVIEW_INDEX")
        self.assertEqual(result["unsupported_index_entries"], 1)
        self.assertEqual(self.manage("install", ok=False)[0].returncode, 2)


if __name__ == "__main__":
    unittest.main()
