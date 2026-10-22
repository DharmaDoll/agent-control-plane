"""Batch contracts: enumeration must not start a detector for each input."""
import importlib.util
from pathlib import Path
import subprocess
import json
import struct
import time
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    "batch_gate", Path(__file__).resolve().parents[1] / "scripts/gitleaks_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class BatchGateTests(unittest.TestCase):
    def scanner(self):
        scanner = gate.Scanner.__new__(gate.Scanner)
        scanner.binary = Path("/unused")
        scanner.docker = None
        scanner.total = 0
        scanner.inputs = []
        scanner.deadline = time.monotonic() + 120
        return scanner

    def test_collection_does_not_launch_per_input_processes(self):
        scanner = gate.Scanner.__new__(gate.Scanner)
        scanner.binary = Path("/unused")
        scanner.docker = None
        scanner.total = 0
        scanner.inputs = []
        with patch.object(gate, "run", return_value=subprocess.CompletedProcess([], 0, b"[]", b"")) as run:
            for value in (b"first.txt", b"ordinary content", b"second.txt"):
                scanner.scan(value, "test")
            self.assertEqual(run.call_count, 0, "collection must not launch per-input detectors")

    def test_one_invocation_with_independent_frames(self):
        scanner = self.scanner()
        for value in (b"first", b"", b"last"):
            scanner.scan(value, "test")
        report = {"version": 1, "complete": True, "processed": 3, "bytes": 9, "findings": []}
        with patch.object(gate, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(report).encode(), b"")) as run:
            scanner.finish()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["data"], struct.pack(">4sIQ", b"SCB1", 3, 9)
                         + struct.pack(">II", 0, 5) + b"first" + struct.pack(">II", 1, 0)
                         + struct.pack(">II", 2, 4) + b"last")

    def test_completion_and_findings_are_strictly_validated(self):
        good = {"version": 1, "complete": True, "processed": 1, "bytes": 4, "findings": []}
        bad = [{**good, "complete": False}, {**good, "processed": 0}, {**good, "bytes": 3},
               {**good, "processed": True}, {**good, "extra": "untrusted"},
               {**good, "findings": [{"input": 1, "rules": ["test"]}]},
               {**good, "findings": [{"input": 0, "rules": ["unsafe\noutput"]}]}]
        for report in bad:
            scanner = self.scanner()
            scanner.scan(b"safe", "test")
            with patch.object(gate, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(report).encode(), b"")):
                with self.assertRaises(gate.Rejected) as caught:
                    scanner.finish()
                self.assertEqual(caught.exception.code, 2)

    def test_deadline_expired_before_launch(self):
        scanner = self.scanner()
        scanner.deadline = 0
        with patch.object(gate, "run") as run:
            with self.assertRaises(gate.Rejected):
                scanner.finish()
            run.assert_not_called()

    def test_docker_receives_one_batch_and_the_original_deadline(self):
        scanner = self.scanner()
        scanner.docker = Mock()
        scanner.image = "sha256:" + "a" * 64
        for _ in range(500):
            scanner.scan(b"safe", "test")
        report = {"version": 1, "complete": True, "processed": 500, "bytes": 2000, "findings": []}
        scanner.docker.scan.return_value = subprocess.CompletedProcess([], 0, json.dumps(report).encode(), b"")
        scanner.finish()
        scanner.docker.scan.assert_called_once()
        self.assertEqual(scanner.docker.scan.call_args.kwargs["deadline"], scanner.deadline)

    def test_transport_budget_is_fail_closed(self):
        scanner = self.scanner()
        with patch.object(gate, "MAX_WIRE", 24):
            with self.assertRaises(gate.Rejected):
                scanner.scan(b"safe", "test")

    def test_release_pins_agree(self):
        import test_manage_hooks as lifecycle
        spec = importlib.util.spec_from_file_location("release_manager", lifecycle.MANAGER)
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
        self.assertEqual(manager.RUNNER_SHA256, gate.BINARY_SHA256)
