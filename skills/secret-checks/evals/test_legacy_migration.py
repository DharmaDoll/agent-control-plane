"""Opt-in migration from the immutable pre-batch repository revision."""
import os
from pathlib import Path
import subprocess
import unittest

import test_manage_hooks as lifecycle

BASELINE = "638efd9154792017cc78863ca00fdafef4219632"


class LegacyMigrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SECRET_CHECKS_LEGACY") == "1", "Opt-in historical checkout fixture required")
    def test_old_bundle_is_preserved_and_rollback_still_executes_it(self):
        runner = os.environ["SECRET_CHECKS_RUNNER"]
        cli = os.environ["SECRET_CHECKS_GITLEAKS"]
        fixture = lifecycle.LifecycleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        old = fixture.root / "legacy skill"
        for name in ("scripts/manage_hooks.py", "scripts/gitleaks_gate.py", "assets/gitleaks.toml",
                     "assets/hooks/pre-commit", "assets/hooks/commit-msg", "assets/hooks/pre-push"):
            result = subprocess.run(["/usr/bin/git", "show", f"{BASELINE}:skills/secret-checks/{name}"],
                                    cwd=lifecycle.SKILL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(result.returncode, 0, "historical fixture unavailable")
            target = old / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(result.stdout)
        fixture.manage("install", "--engine", "gitleaks", "--runtime", "native", "--gitleaks", cli,
                       script=old / "scripts/manage_hooks.py")
        original = fixture.state()["active"]
        before = fixture.state()
        _, refused = fixture.manage("update", ok=False)
        self.assertEqual(refused["reason"], "VERIFIED_GITLEAKS_RUNNER_REQUIRED")
        self.assertEqual(fixture.state(), before)
        fixture.manage("update", "--gitleaks-runner", runner)
        current = fixture.state()["active"]
        self.assertNotEqual(current, original)
        self.assertTrue((fixture.bundle(original) / "bin/gitleaks").exists())
        self.assertTrue((fixture.bundle(current) / "bin/gitleaks-runner").exists())
        fixture.manage("rollback")
        self.assertEqual(fixture.state()["active"], original)
        fixture.manage("verify")
        fixture.manage("rollback")
        self.assertEqual(fixture.state()["active"], current)
        fixture.manage("uninstall")
        fixture.manage("cleanup", "--apply")
        self.assertFalse(fixture.bundle(original).exists())
        self.assertFalse(fixture.bundle(current).exists())
