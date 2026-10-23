#!/usr/bin/env python3
"""Offline, synthetic worst-case probes; no fixture contents are printed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan_sensitive as scanner


def fixtures(size: int):
    def fill(unit: bytes) -> bytes:
        return (unit * (size // len(unit) + 1))[:size]
    return {
        "plain": b"a" * size,
        "whitespace": b" " * size,
        "whitespace-lines": fill(b" \n"),
        "near-prefixes": fill(b"sk-proj-! glpat-! hf_! npm_! re_! vcp_! "),
        "near-assignments": fill(b'"password" : "short", export OPENAI_API_KEY=$VALUE\n'),
        "near-urls": fill(b"https://user@host.invalid/ Authorization: Basic !!!\n"),
        "long-suffix": b"https://" + b"a" * (size - 8),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bytes", type=int, default=scanner.MAX_FILE_BYTES)
    parser.add_argument("--deadline", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.bytes <= scanner.MAX_FILE_BYTES or args.deadline < 1:
        parser.error("invalid probe limits")

    def expired(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, expired)
    failed = False
    for name, content in fixtures(args.bytes).items():
        scanner._total = scanner._items = 0
        started = time.perf_counter()
        signal.alarm(args.deadline)
        try:
            findings = scanner.scan("benchmark.txt", content)
            status = "clean" if not findings else "finding"
        except TimeoutError:
            status = "timeout"
        except scanner.ScanError:
            status = "incomplete"
        finally:
            signal.alarm(0)
        elapsed = time.perf_counter() - started
        print(json.dumps({"case": name, "bytes": len(content),
                          "seconds": round(elapsed, 4), "status": status}), flush=True)
        failed |= status != "clean"
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
