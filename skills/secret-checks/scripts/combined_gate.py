#!/usr/bin/env python3
"""Run both bundled engines in order; only two successful checks permit Git."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MAX_INPUT = 65536
CHILD_TIMEOUT = 125


def run_engine(script, args, data):
    """Discard child diagnostics, including unexpected tracebacks and payloads."""
    try:
        with subprocess.Popen(
            [sys.executable, "-I", "-B", str(ROOT / script), *args],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        ) as child:
            try:
                child.communicate(input=data, timeout=CHILD_TIMEOUT)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate()
                return 2
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
        result = run_engine(script, argv, data)
        results.append(result)
        status = ("CHECKED", "REJECTED", "ERROR")[result]
        print(f"{status} engine:{engine}", file=sys.stderr)
    # Incomplete evidence takes precedence over findings; neither can permit Git.
    return 2 if 2 in results else (1 if 1 in results else 0)


if __name__ == "__main__":
    raise SystemExit(main())
