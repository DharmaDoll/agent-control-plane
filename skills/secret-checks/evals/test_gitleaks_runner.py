"""Real pinned CLI/runner parity; never print synthetic secret payloads."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

import test_gitleaks_gate as existing

ROOT = Path(__file__).resolve().parents[1]


def frame(items):
    return (struct.pack(">4sIQ", b"SCB1", len(items), sum(map(len, items)))
            + b"".join(struct.pack(">II", i, len(value)) + value for i, value in enumerate(items)))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = os.environ.get("SECRET_CHECKS_RUNNER")
        if not self.runner:
            self.skipTest("SECRET_CHECKS_RUNNER required")
        self.assertEqual(hashlib.sha256(Path(self.runner).read_bytes()).hexdigest(),
                         existing.manage_hooks.RUNNER_SHA256)
        self.config = str(ROOT / "assets/gitleaks.toml")

    def invoke(self, raw, env=None):
        return subprocess.run([self.runner, "--config", self.config], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                              env=env or {"PATH": "/usr/bin:/bin", "GOTRACEBACK": "none"})

    def test_batch_beginning_middle_end_findings_and_no_disclosure(self):
        for position in (0, 250, 499):
            items = [f"ordinary text {i}\n".encode() for i in range(500)]
            items[position] = existing.CANARY
            result = self.invoke(frame(items))
            self.assertEqual(result.returncode, 10)
            report = json.loads(result.stdout)
            self.assertEqual(report["processed"], 500)
            self.assertTrue(report["complete"])
            self.assertEqual([f["input"] for f in report["findings"]], [position])
            self.assertNotIn(existing.CANARY, result.stdout + result.stderr)
            self.assertEqual(result.stderr, b"")

    def test_malformed_truncated_oversized_and_unsupported_input(self):
        good = frame([b"safe"])
        for raw in (b"", b"SCB2", good[:-1], good + b"x", frame([b"\0"]), frame([b"\xff"]),
                    frame([b"a" * (2 * 1024 * 1024 + 1)]),
                    struct.pack(">4sIQ", b"SCB1", 1, 32 * 1024 * 1024 + 1)):
            result = self.invoke(raw)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"ERROR batch scan incomplete\n")

    def test_empty_batch_and_empty_input_are_completed(self):
        for items in ([], [b""]):
            result = self.invoke(frame(items))
            self.assertEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertTrue(report["complete"])
            self.assertEqual(report["processed"], len(items))

    def test_official_cli_parity_and_input_isolation(self):
        cli = os.environ.get("SECRET_CHECKS_GITLEAKS")
        if not cli:
            self.skipTest("SECRET_CHECKS_GITLEAKS required for independent comparison")
        self.assertEqual(hashlib.sha256(Path(cli).read_bytes()).hexdigest(), existing.manage_hooks.GITLEAKS_SHA256)
        token = b"ghp_" + hashlib.sha256(b"inert regression fixture not an issued credential").hexdigest()[:36].encode()
        items = [b"", b"ordinary\n", existing.CANARY, token, token + b" # gitleaks:allow\n",
                 b"ghp_", token[4:], b"\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\n",
                 b"a\n" * 50000 + token, b"a" * 100001 + b"\n" + existing.CANARY,
                 b"%PDF-1.0\n" + token, b"-----BEGIN PRIVATE " , b"KEY-----\n" + b"x" * 100,
                 b"a" * 24950 + b"\n" + existing.CANARY,
                 b"AKIA" + b"Q6D2N5F4Z6H3V7J5"]
        expected = []
        for i, item in enumerate(items):
            r = subprocess.run([cli, "stdin", "--config", self.config,
                "--gitleaks-ignore-path", "/dev/null", "--ignore-gitleaks-allow",
                "--redact=100", "--no-banner", "--no-color", "--log-level=error",
                "--max-decode-depth=0", "--max-archive-depth=0", "--timeout=10",
                "--exit-code=10", "--report-format=json", "--report-path=-"],
                input=b"source002 text input\n" + item, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=30, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
            self.assertIn(r.returncode, (0, 10), "comparison CLI incomplete")
            rules = sorted({f["RuleID"] for f in json.loads(r.stdout)})
            if rules:
                expected.append({"input": i, "rules": rules})
        self.assertGreaterEqual(len({rule for finding in expected for rule in finding["rules"]}), 3)
        result = self.invoke(frame(items), env={"PATH": "/usr/bin:/bin", "GOTRACEBACK": "none",
                                              "GITLEAKS_CONFIG_TOML": "invalid override"})
        self.assertEqual(result.returncode, 10)
        report = json.loads(result.stdout)
        self.assertEqual(report["findings"], expected)
        self.assertEqual(report["processed"], len(items))
        self.assertEqual(result.stderr, b"")
