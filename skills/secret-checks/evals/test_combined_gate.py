"""Dispatcher contracts with inert child fixtures; real engines tested separately."""
import importlib.util
import itertools
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/combined_gate.py"
spec = importlib.util.spec_from_file_location("combined_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class CombinedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="combined-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copyfile(SCRIPT, self.root / SCRIPT.name)

    def child(self, filename, code):
        (self.root / filename).write_text(code)

    def test_default_commit_skips_gitleaks_but_push_requires_it(self):
        self.child('scan_sensitive.py', 'raise SystemExit(0)\n')
        # No Gitleaks child exists: commit must work, push must fail closed.
        for args in (('pre-commit',), ('commit-msg', 'message')):
            result = self.call(*args)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b'SKIPPED engine:gitleaks policy:commit-disabled', result.stderr)
            self.assertNotIn(b'CHECKED engine:gitleaks', result.stderr)
        result = self.call('pre-push', 'origin', 'remote')
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'ERROR engine:gitleaks', result.stderr)

    def call(self, *args, data=b""):
        return subprocess.run([sys.executable, "-I", "-B", str(self.root / SCRIPT.name), *args],
                              input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=15)

    def test_status_matrix_runs_both_in_order_and_suppresses_child_output(self):
        for first, second in itertools.product((0, 1, 2, 7), repeat=2):
            with self.subTest(first=first, second=second):
                for filename, code, marker in (
                    ("scan_sensitive.py", first, "python"),
                    ("gitleaks_gate.py", second, "gitleaks"),
                ):
                    self.child(filename, f"""
from pathlib import Path
import sys
with (Path(__file__).parent / "order").open("a") as stream:
    stream.write("{marker}\\n")
print("inert-private-diagnostic")
print("inert-private-diagnostic", file=sys.stderr)
raise SystemExit({code})
""")
                result = self.call("pre-push", "origin", "remote")
                expected = 2 if any(c not in (0, 1) for c in (first, second)) else max(first, second)
                self.assertEqual(result.returncode, expected)
                self.assertNotIn(b"inert-private-diagnostic", result.stdout + result.stderr)
                order = self.root / "order"
                self.assertEqual(order.read_text(), "python\ngitleaks\n")
                order.unlink()

    def test_push_stdin_is_replayed_and_arguments_are_preserved(self):
        for filename, marker in (("scan_sensitive.py", "python"), ("gitleaks_gate.py", "gitleaks")):
            self.child(filename, f"""
import json, sys
from pathlib import Path
root = Path(__file__).parent
(root / "{marker}.input").write_bytes(sys.stdin.buffer.read())
(root / "{marker}.args").write_text(json.dumps(sys.argv[1:]))
""")
        data = b"refs/heads/main " + b"a" * 40 + b" refs/heads/main " + b"0" * 40 + b"\n"
        result = self.call("pre-push", "origin", "local remote with spaces", data=data)
        self.assertEqual(result.returncode, 0)
        for marker in ("python", "gitleaks"):
            self.assertEqual((self.root / (marker + ".input")).read_bytes(), data)
        import json
        self.assertEqual(json.loads((self.root / "python.args").read_text()), ["--pre-push"])
        self.assertEqual(json.loads((self.root / "gitleaks.args").read_text()),
                         ["pre-push", "origin", "local remote with spaces"])

    def test_message_path_is_one_argument_and_not_shell_code(self):
        path = "message with spaces;$(not-a-command)"
        with patch.object(sys, "argv", ["combined_gate.py", "commit-msg", path]), \
                patch.object(gate, 'COMMIT_GITLEAKS', True), \
                patch.object(gate, "run_engine", return_value=0) as run:
            self.assertEqual(gate.main(), 0)
        self.assertEqual(run.call_args_list[0].args,
                         ("scan_sensitive.py", ["--file", path, "--label", "commit-message"], b""))
        self.assertEqual(run.call_args_list[1].args,
                         ("gitleaks_gate.py", ["commit-msg", path], b""))

    def test_missing_engine_cannot_pass(self):
        self.child("gitleaks_gate.py", "raise SystemExit(0)\n")
        result = self.call("pre-push", "origin", "remote")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"ERROR engine:python", result.stderr)
        self.assertIn(b"CHECKED engine:gitleaks", result.stderr)

    def test_only_allowlisted_policy_diagnostics_cross_boundary(self):
        self.child('scan_sensitive.py', '''
print("POLICY images_allowed:2 image_content:unscanned")
print("ERROR policy commit-files actual:101 limit:100")
print("ERROR policy private-untrusted-diagnostic")
print("ERROR policy commit-files actual:101 limit:100 EXTRA")
raise SystemExit(2)
''')
        self.child('gitleaks_gate.py', 'raise SystemExit(0)\n')
        result = self.call('pre-commit')
        self.assertIn(b'images_allowed:2', result.stderr)
        self.assertIn(b'commit-files actual:101 limit:100', result.stderr)
        self.assertNotIn(b'private-untrusted', result.stderr)
        self.assertNotIn(b'EXTRA', result.stderr)

    def test_invalid_invocation_and_oversized_stdin_refuse_before_children(self):
        for args, data in (([], b""), (["unknown"], b""),
                           (["pre-push"], b""),
                           (["pre-push", "origin", "remote"], b"x" * 65537)):
            result = self.call(*args, data=data)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"engine:", result.stderr)

    def test_timeout_and_launch_failure_are_incomplete(self):
        self.child("slow.py", "import time\ntime.sleep(30)\n")
        with patch.object(gate, "ROOT", self.root), patch.object(gate, "CHILD_TIMEOUT", 0.05):
            self.assertEqual(gate.run_engine("slow.py", [], b""), 2)
        with patch.object(gate.subprocess, "Popen", side_effect=OSError("inert diagnostic")):
            self.assertEqual(gate.run_engine("unused.py", [], b""), 2)


if __name__ == "__main__":
    unittest.main()
