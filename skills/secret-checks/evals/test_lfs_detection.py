"""LFS metadata is not an arbitrary substring; admitted text still gets scanned."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

import test_gitleaks_gate as existing

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lfs_python", ROOT / "scripts/scan_sensitive.py")
python_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(python_scanner)

VERSIONS = (b"https://git-lfs.github.com/spec/v1", b"https://hawser.github.com/spec/v1",
            b"http://git-media.io/v/2")
HEADER = b"version " + VERSIONS[0]
SOURCE = b'pointer_header = "' + HEADER + b'"\n'


def refused_inputs():
    for version in VERSIONS:
        header = b"version " + version
        yield header  # Truncated metadata must not be considered clean content.
        yield header + b"\noid sha256:" + b"0" * 64 + b"\nsize 1\n"
        yield header + b"\r\noid sha256:" + b"0" * 64 + b"\r\nsize 1\r\n"
        yield b"\xc2\xa0 \n\t" + header + b" \r\nsize invalid\n"
        yield header + b"\next-0-test sha256:" + b"0" * 64 + b"\noid invalid\n"
    # Conservatively refuse standalone metadata even in a fenced example.
    yield b"```text\n" + HEADER + b"\n```\n"


class LFSPolicyTests(unittest.TestCase):
    def adapter(self):
        scanner = existing.gate.Scanner.__new__(existing.gate.Scanner)
        scanner.total, scanner.inputs = 0, []
        return scanner

    def setUp(self):
        python_scanner._total = python_scanner._items = 0

    def test_embedded_source_and_inline_documentation_are_scanned(self):
        for data in (SOURCE, b"Compare `" + HEADER + b"` in the parser.\n",
                     b'if b"' + HEADER + b'" in value:\n    pass\n', b""):
            self.assertEqual(python_scanner.scan("source.txt", data), [])
            scanner = self.adapter()
            scanner.scan(data, "source.txt")
            self.assertEqual(scanner.inputs, [data])

    def test_pointer_headers_remain_incomplete(self):
        for i, data in enumerate(refused_inputs()):
            with self.subTest(case=i):
                with self.assertRaises(python_scanner.ScanError):
                    python_scanner.scan("source.txt", data)
                with self.assertRaises(existing.gate.Rejected) as caught:
                    self.adapter().scan(data, "source.txt")
                self.assertEqual(caught.exception.code, 2)

    def test_embedded_header_does_not_exempt_secrets(self):
        findings = python_scanner.scan("source.txt", SOURCE + existing.CANARY)
        self.assertIn("private-key", {rule for rule, _ in findings})


class LFSRunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = os.environ.get("SECRET_CHECKS_RUNNER")
        if not self.runner:
            self.skipTest("SECRET_CHECKS_RUNNER required")
        self.assertEqual(hashlib.sha256(Path(self.runner).read_bytes()).hexdigest(),
                         existing.manage_hooks.RUNNER_SHA256)

    def invoke(self, data):
        frame = struct.pack(">4sIQII", b"SCB1", 1, len(data), 0, len(data)) + data
        return subprocess.run([self.runner, "--config", str(ROOT / "assets/gitleaks.toml")],
                              input=frame, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, env={"PATH": "/usr/bin:/bin", "GOTRACEBACK": "none"})

    def test_embedded_header_is_scanned_not_exempted(self):
        for data, code in ((SOURCE, 0), (SOURCE + existing.CANARY, 10)):
            result = self.invoke(data)
            self.assertEqual(result.returncode, code)
            report = json.loads(result.stdout)
            self.assertTrue(report["complete"])
            self.assertEqual(report["processed"], 1)
            self.assertEqual(bool(report["findings"]), code == 10)
            self.assertNotIn(existing.CANARY, result.stdout + result.stderr)

    def test_pointer_headers_remain_incomplete(self):
        for i, data in enumerate(refused_inputs()):
            with self.subTest(case=i):
                result = self.invoke(data)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"ERROR batch scan incomplete\n")
