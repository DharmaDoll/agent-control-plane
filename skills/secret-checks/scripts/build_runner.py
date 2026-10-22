#!/usr/bin/env python3
"""Offline, reproducible build of the reviewed runner; never installs hooks."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", type=Path, required=True, help="Approved Go 1.26.8 executable")
    parser.add_argument("--module-cache", type=Path, required=True, help="Pre-acquired, checksum-verified modules")
    parser.add_argument("--output", type=Path, required=True, help="New artifact path; never overwritten")
    args = parser.parse_args()
    try:
        if not args.go.is_absolute() or not args.module_cache.is_absolute() or not args.output.is_absolute():
            raise ValueError
        if args.output.exists() or args.output.is_symlink():
            raise ValueError
        spec = importlib.util.spec_from_file_location("reviewed_manager", ROOT / "scripts/manage_hooks.py")
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
        with tempfile.TemporaryDirectory(prefix="secret-checks-build-", dir=args.output.parent) as raw:
            temp = Path(raw)
            env = {"PATH": "/usr/bin:/bin", "GOTOOLCHAIN": "local", "GOENV": "off", "GOWORK": "off",
                   "GOPROXY": "off", "GOSUMDB": "off", "CGO_ENABLED": "0", "GOOS": "linux",
                   "GOARCH": "amd64", "GOAMD64": "v1", "GOEXPERIMENT": "", "GOCACHE": str(temp / "cache"),
                   "GOMODCACHE": str(args.module_cache), "GOPATH": str(temp / "gopath"), "HOME": str(temp)}
            def call(*arguments):
                result = subprocess.run([str(args.go), *arguments], cwd=ROOT / "runner", env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
                if result.returncode:
                    raise ValueError
                return result.stdout
            if call("version").strip() != b"go version go1.26.8 linux/amd64":
                raise ValueError
            call("mod", "verify")
            artifact = temp / "gitleaks-runner"
            call("build", "-mod=readonly", "-tags=gore2regex", "-trimpath", "-buildvcs=false",
                 "-ldflags=-s -w -buildid=", "-o", str(artifact), ".")
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != manager.RUNNER_SHA256:
                raise ValueError
            artifact.chmod(0o700)
            os.link(artifact, args.output)  # Atomic create, not replace; temp is on the same filesystem.
        print("PASS reviewed runner built and digest verified")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print("BLOCKED toolchain, modules, output path, build, or digest verification failed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
