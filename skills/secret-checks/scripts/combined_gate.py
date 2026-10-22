#!/usr/bin/env python3
"""Run Python on every hook and Gitleaks on push (optionally also on commit)."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MAX_INPUT = 65536
CHILD_TIMEOUT = 125
COMMIT_GITLEAKS = False  # Fixed at bundle creation, never read from target config/env.


def diagnostics(script, output):
    """Relay only fixed policy messages, never arbitrary child diagnostics."""
    engine = {'scan_sensitive.py': 'python', 'gitleaks_gate.py': 'gitleaks'}.get(script)
    if engine is None:
        return
    codes = ('git-unavailable|git-incomplete|object-enumeration-limit|'
             'object-metadata-incomplete|object-metadata-invalid|unsupported-index|'
             'index-changed-during-check|invalid-index-object|hook-input-limit|'
             'invalid-hook-input|invalid-object-id|unsupported-ref|invalid-object-enumeration|'
             'image-bytes-limit|image-scan-budget|image-signature-mismatch')
    allowed = re.compile(rb'(?:ERROR policy (?:(?:' + codes.encode() + rb')|'
                         rb'(?:commit|push)-(?:files|bytes) actual:[0-9]{1,12} limit:[0-9]{1,12})|'
                         rb'POLICY images_allowed:[0-9]{1,4} image_content:unscanned)')
    for line in output.splitlines():
        if allowed.fullmatch(line):
            print(f'DETAIL engine:{engine} ' + line.decode('ascii'), file=sys.stderr)


def run_engine(script, args, data):
    """Discard child diagnostics, including unexpected tracebacks and payloads."""
    try:
        with subprocess.Popen(
            [sys.executable, "-I", "-B", str(ROOT / script), *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        ) as child:
            try:
                stdout, stderr = child.communicate(input=data, timeout=CHILD_TIMEOUT)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate()
                return 2
            if len(stdout) + len(stderr) > 65536:
                return 2
            diagnostics(script, stdout + b'\n' + stderr)
            return child.returncode if child.returncode in (0, 1, 2) else 2
    except OSError:
        return 2


def main():
    mode, *args = sys.argv[1:] or [""]
    data = b""
    if mode == "pre-commit" and not args:
        python_args = ["--staged"]
    elif mode == "commit-msg" and len(args) == 1:
        python_args = ["--file", args[0], "--label", "commit-message"]
    elif mode == "pre-push" and len(args) == 2:
        python_args = ["--pre-push"]

        def deadline(_signum, _frame):
            raise TimeoutError

        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(5)
        try:
            # Read once, then replay identical bytes to both independent consumers.
            data = sys.stdin.buffer.read(MAX_INPUT + 1)
        except (OSError, TimeoutError):
            print("ERROR combined input unavailable or incomplete", file=sys.stderr)
            return 2
        finally:
            signal.alarm(0)
        if len(data) > MAX_INPUT:
            print("ERROR combined input limit exceeded", file=sys.stderr)
            return 2
    else:
        print("ERROR invalid combined invocation", file=sys.stderr)
        return 2

    results = []
    for engine, script, argv in (
        ("python", "scan_sensitive.py", python_args),
        ("gitleaks", "gitleaks_gate.py", [mode, *args]),
    ):
        if engine == "gitleaks" and mode != "pre-push" and not COMMIT_GITLEAKS:
            print("SKIPPED engine:gitleaks policy:commit-disabled", file=sys.stderr)
            continue
        result = run_engine(script, argv, data)
        results.append(result)
        status = ("CHECKED", "REJECTED", "ERROR")[result]
        print(f"{status} engine:{engine}", file=sys.stderr)
    # Incomplete evidence takes precedence over findings; neither can permit Git.
    return 2 if 2 in results else (1 if 1 in results else 0)


if __name__ == "__main__":
    raise SystemExit(main())
