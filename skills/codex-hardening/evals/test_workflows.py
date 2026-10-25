"""Opt-in offline workflow evidence; never install tools or use real projects."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

from test_harden import h


@unittest.skipUnless(os.environ.get("CODEX_HARDENING_WORKFLOWS") == "1",
                     "offline native workflow tests are opt-in")
class OfflineWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ["CODEX_HARDENING_BINARY"])
        cls.identity, version, recipe = h.detect(cls.binary)
        if version != os.environ.get("CODEX_HARDENING_EXPECTED_VERSION") or recipe is None:
            raise RuntimeError("explicit expected supported CLI version required")

    @classmethod
    def tearDownClass(cls):
        if h.executable_identity(cls.binary) != cls.identity:
            raise RuntimeError("native CLI changed during workflow tests")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="codex-hardening-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home, self.work = self.root / "home", self.root / "workspace"
        self.home.mkdir()
        self.work.mkdir()
        (self.home / "acp-development.config.toml").write_text(h.render_profile("development"))

    def tool(self, name):
        executable = shutil.which(name)
        if executable is None:
            self.skipTest(name + " is not installed; no automatic installation")
        return executable

    def run_case(self, label, command, sandbox=True):
        if sandbox:
            command = [str(self.binary), "sandbox", "--profile", "acp-development",
                       "--permission-profile", "acp-development", "--cd", str(self.work), "--", *command]
        started = time.monotonic()
        result = h.run(command, self.home, self.work, timeout=90)
        print(json.dumps({"workflow": label, "sandbox": sandbox, "exit_code": result[0],
                          "seconds": round(time.monotonic() - started, 3)}), flush=True)
        return result

    def test_python_stdlib_tests_and_workspace_write(self):
        (self.work / "test_fixture.py").write_text(
            'import unittest\nfrom pathlib import Path\n'
            'class Fixture(unittest.TestCase):\n'
            '    def test_sum(self):\n'
            '        self.assertEqual(sum([2, 3]), 5)\n'
            '        Path("python-result").write_text("passed")\n')
        rc, _, err = self.run_case("python-unittest", [sys.executable, "-I", "-B", "-m",
                                                     "unittest", "discover", "-s", str(self.work)])
        self.assertEqual(rc, 0, "Python workflow failed")
        self.assertIn(b"Ran 1 test", err)
        self.assertEqual((self.work / "python-result").read_text(), "passed")

    def test_node_builtin_tests_and_workspace_write(self):
        node = self.tool("node")
        (self.work / "fixture.test.cjs").write_text(
            'const test = require("node:test");\n'
            'const assert = require("node:assert/strict");\n'
            'const fs = require("node:fs");\n'
            'test("sum", () => { assert.equal(2 + 3, 5); fs.writeFileSync("node-result", "passed"); });\n')
        rc, out, _ = self.run_case("node-test", [node, "--test", "fixture.test.cjs"])
        self.assertEqual(rc, 0, "Node workflow failed")
        self.assertIn(b"pass 1", out)
        self.assertEqual((self.work / "node-result").read_text(), "passed")

    def test_go_requires_explicit_workspace_cache_and_temp(self):
        go, env = self.tool("go"), self.tool("env")
        (self.work / "go.mod").write_text("module example.invalid/acp-fixture\n\ngo 1.18\n")
        (self.work / "sum.go").write_text("package fixture\nfunc Sum(a, b int) int { return a + b }\n")
        (self.work / "sum_test.go").write_text(
            'package fixture\nimport "testing"\n'
            'func TestSum(t *testing.T) { if Sum(2, 3) != 5 { t.Fatal("sum") }; t.TempDir() }\n')
        offline = [env, "GOENV=off", "GOWORK=off", "GOPROXY=off", "GOSUMDB=off",
                   "GOTOOLCHAIN=local", "GOTELEMETRY=off", "CGO_ENABLED=0"]
        # The first attempt deliberately uses the ordinary HOME cache/temp
        # placement. This expected failure measures friction, not broken code.
        rc, _, err = self.run_case("go-default-cache", [*offline, go, "test", "-count=1", "./..."])
        self.assertNotEqual(rc, 0)
        self.assertTrue(b"permission denied" in err or b"read-only file system" in err,
                        "Go failure was not attributable to filesystem restrictions")
        build = self.work / ".build"
        for name in ("cache", "tmp", "modules", "gopath"):
            (build / name).mkdir(parents=True)
        # Explicit fixture-local tool configuration, not a permission change
        # or automatic agent fallback. Both attempts stay inside the sandbox.
        local = [*offline, f"GOCACHE={build / 'cache'}", f"GOTMPDIR={build / 'tmp'}",
                 f"TMPDIR={build / 'tmp'}", f"GOMODCACHE={build / 'modules'}",
                 f"GOPATH={build / 'gopath'}", go, "test", "-count=1", "./..."]
        rc, out, _ = self.run_case("go-workspace-cache", local)
        self.assertEqual(rc, 0, "offline Go tests failed with fixture-local cache/temp")
        self.assertIn(b"ok", out)

    def test_git_control_success_then_sandbox_write_denial(self):
        git = self.tool("git")
        args = [git, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgSign=false"]
        # These unsandboxed positive controls are explicitly part of this
        # isolated test. There is no retry outside the sandbox after a denial.
        commands = [(*args, "init", "--template="),
                    (*args, "init", "--bare", "--template=", str(self.root / "remote.git"))]
        for command in commands:
            self.assertEqual(self.run_case("git-fixture-init", list(command), sandbox=False)[0], 0)
        tracked = self.work / "fixture.txt"
        tracked.write_text("first fixture\n")
        for command in ([*args, "add", "--", "fixture.txt"],
                        [*args, "commit", "-m", "fixture baseline"],
                        [*args, "push", str(self.root / "remote.git"), "HEAD:refs/heads/main"]):
            self.assertEqual(self.run_case("git-local-control", command, sandbox=False)[0], 0)
        rc, original, _ = h.run([*args, "rev-parse", "HEAD"], self.home, self.work)
        self.assertEqual(rc, 0)
        rc, remote, _ = h.run([git, "--git-dir", str(self.root / "remote.git"), "rev-parse", "refs/heads/main"],
                              self.home, self.work)
        self.assertEqual((rc, remote), (0, original))
        tracked.write_text("second fixture\n")
        for command in ([*args, "add", "--", "fixture.txt"],
                        [*args, "commit", "--allow-empty", "-m", "must be denied"]):
            rc, _, err = self.run_case("git-denial", command)
            self.assertNotEqual(rc, 0)
            self.assertTrue(b"Permission denied" in err or b"Read-only file system" in err,
                            "Git failure was not attributable to filesystem restrictions")
        rc, current, _ = h.run([*args, "rev-parse", "HEAD"], self.home, self.work)
        self.assertEqual((rc, current), (0, original))
        rc, diff, _ = h.run([*args, "diff", "--cached", "--name-only"], self.home, self.work)
        self.assertEqual((rc, diff), (0, b""))


if __name__ == "__main__":
    unittest.main()
