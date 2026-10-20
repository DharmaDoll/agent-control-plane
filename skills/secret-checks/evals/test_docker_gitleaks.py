"""Docker command contracts; opt-in real Docker checks use inert Git fixtures."""
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import test_manage_hooks as lifecycle

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/docker_gitleaks.py"
spec = importlib.util.spec_from_file_location("docker_runtime_test", SCRIPT)
docker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker)
IMAGE = "sha256:" + "a" * 64
CID = "b" * 64


def result(code=0, output=b""):
    return subprocess.CompletedProcess([], code, output, b"untrusted diagnostic")


class DockerContractTests(unittest.TestCase):
    def test_invalid_manifest_never_selects_native(self):
        scanner_spec = importlib.util.spec_from_file_location(
            "docker_manifest_gate", SCRIPT.parent / "gitleaks_gate.py")
        gate = importlib.util.module_from_spec(scanner_spec)
        scanner_spec.loader.exec_module(gate)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "bin").mkdir()
            (root / "bin/gitleaks").write_bytes(b"inert")
            with patch.object(gate, "BUNDLE", root), patch.object(gate, "RUNTIME", "docker"), \
                    patch.object(gate, "BINARY_SHA256", hashlib.sha256(b"inert").hexdigest()):
                for value in (None, b"[]", b"{", b"x" * 4097):
                    if value is not None:
                        (root / "docker-image.json").write_bytes(value)
                    with self.assertRaises(gate.Rejected):
                        gate.Scanner()

    def sequence(self, code=0):
        return [result(output=IMAGE.encode()), result(output=CID.encode()),
                result(output=b"[]" if code == 0 else b'[{"RuleID":"inert"}]'),
                result(output=json.dumps({"Running": False, "OOMKilled": False,
                                          "Error": "", "ExitCode": code}).encode()),
                result()]

    def test_hardened_stdin_execution_and_exact_cleanup(self):
        for code in (0, 10):
            with patch.object(docker, "command", side_effect=self.sequence(code)) as command:
                actual = docker.scan(IMAGE, ["stdin"], b"inert input")
            self.assertEqual(actual.returncode, code)
            create = command.call_args_list[1].args[0]
            for flag in ("--pull=never", "--network=none", "--read-only",
                         "--user=65532:65532", "--cap-drop=ALL",
                         "--security-opt=no-new-privileges", "--log-driver=none"):
                self.assertIn(flag, create)
            self.assertFalse(any("mount" in arg or "volume" in arg for arg in create))
            self.assertEqual(command.call_args_list[2].kwargs["data"], b"inert input")
            self.assertEqual(command.call_args_list[-1].args[0], ["rm", "--force", CID])

    def test_attach_timeout_still_removes_owned_container(self):
        outcomes = self.sequence()[:2] + [RuntimeError("DOCKER_UNAVAILABLE_OR_TIMEOUT"), result()]
        with patch.object(docker, "command", side_effect=outcomes) as command:
            with self.assertRaises(RuntimeError):
                docker.scan(IMAGE, ["stdin"], b"")
        self.assertEqual(command.call_args_list[-1].args[0], ["rm", "--force", CID])

    def test_invalid_create_result_never_deletes_unknown_container(self):
        with patch.object(docker, "command", side_effect=[
            result(output=IMAGE.encode()), result(1, b"untrusted")]) as command:
            with self.assertRaises(RuntimeError):
                docker.scan(IMAGE, [], b"")
        self.assertEqual(command.call_count, 2)

    def test_cleanup_failure_cannot_report_success(self):
        outcomes = self.sequence()
        outcomes[-1] = result(1)
        with patch.object(docker, "command", side_effect=outcomes):
            with self.assertRaises(RuntimeError):
                docker.scan(IMAGE, [], b"")

    def test_oom_or_unexpected_exit_cannot_report_success(self):
        for state in ({"Running": False, "OOMKilled": True, "Error": "", "ExitCode": 0},
                      {"Running": False, "OOMKilled": False, "Error": "", "ExitCode": 137},
                      {"Running": True, "OOMKilled": False, "Error": "", "ExitCode": 0}):
            outcomes = self.sequence()
            outcomes[3] = result(output=json.dumps(state).encode())
            with patch.object(docker, "command", side_effect=outcomes):
                with self.assertRaises(RuntimeError):
                    docker.scan(IMAGE, [], b"")

    def test_build_context_contains_only_reviewed_inputs(self):
        with patch.object(docker, "command", side_effect=[
            result(output=IMAGE.encode()), result(output=IMAGE.encode())]) as command:
            self.assertEqual(docker.build_image(b"inert binary", b"inert config"), IMAGE)
        args = command.call_args_list[0].args[0]
        self.assertIn("--network=none", args)
        self.assertIn("--pull=false", args)
        with tarfile.open(fileobj=io.BytesIO(command.call_args_list[0].kwargs["data"])) as archive:
            self.assertEqual(archive.getnames(), ["Dockerfile", "gitleaks", "gitleaks.toml"])
            self.assertEqual(archive.extractfile("gitleaks").read(), b"inert binary")

    def test_image_tags_and_missing_images_refused(self):
        with patch.object(docker, "command", return_value=result(1)) as command:
            with self.assertRaises(RuntimeError):
                docker.verify_image("gitleaks:latest")
            command.assert_not_called()
            with self.assertRaises(RuntimeError):
                docker.verify_image(IMAGE)


class DockerLiveTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SECRET_CHECKS_DOCKER") == "1", "Opt-in local Docker required")
    def test_combined_docker_lifecycle(self):
        fixture = lifecycle.LifecycleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        binary = os.environ["SECRET_CHECKS_GITLEAKS"]
        _, installed = fixture.manage("install", "--engine", "combined",
                                       "--gitleaks", binary)
        self.assertEqual(installed["runtime"], "docker")
        _, inspection = fixture.manage("inspect")
        self.assertEqual(inspection["runtime"], "docker")
        self.assertEqual(len(inspection["docker_images"]), 1)
        _, unchanged = fixture.manage("update")
        self.assertEqual(unchanged["runtime"], "docker")
        fixture.manage("verify")
        fixture.stage()
        fixture.git("commit", "-q", "-m", "safe Docker probe")
        manifest = fixture.bundle() / "docker-image.json"
        original = manifest.read_bytes()
        manifest.unlink()
        blocked = fixture.git("commit", "--allow-empty", "-q", "-m", "missing manifest", ok=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn(b"ERROR engine:gitleaks", blocked.stderr)
        manifest.write_bytes(original)
        manifest.chmod(0o600)
        fixture.manage("update", "--runtime", "native")
        fixture.manage("rollback")
        self.assertEqual(fixture.manage("inspect")[1]["runtime"], "docker")
        fixture.manage("uninstall")
        _, cleaned = fixture.manage("cleanup", "--apply")
        self.assertEqual(cleaned["docker_images_retained"], inspection["docker_images"])
        self.assertFalse(fixture.bundle(installed["active"]).exists())


if __name__ == "__main__":
    unittest.main()
