#!/usr/bin/env python3
"""Opt-in real-hook benchmark with isolated, unique benign Git blobs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_manager", ROOT / "scripts/manage_hooks.py")
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--runtime", choices=("native", "docker"), required=True)
    parser.add_argument("--engine", choices=("gitleaks", "combined"), default="gitleaks")
    parser.add_argument("--counts", type=int, nargs="+", default=[10, 150, 236, 500])
    args = parser.parse_args()
    if any(n < 1 or n > 1000 for n in args.counts):
        parser.error("counts must be between 1 and 1000")
    # This measures Gitleaks, so explicitly opt in on commit for combined mode.
    payload = manager.source_payload(args.engine, runtime=args.runtime, runner=args.runner,
                                     commit_gitleaks=args.engine == 'combined')
    with tempfile.TemporaryDirectory(prefix="secret-checks-benchmark-") as raw:
        root = Path(raw)
        bundle = root / "bundle"
        for name, (data, mode) in payload.items():
            target = bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
        env = {"PATH": "/usr/bin:/bin", "HOME": raw, "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "LANG": "C.UTF-8",
               "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
               "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        for count in args.counts:
            repo = root / f"work-{count}"
            subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], env=env, check=True)
            names = []
            total = 0
            for i in range(count):
                name = f"ordinary-{i:04d}.txt"
                data = f"ordinary unique benchmark content {i}\n".encode()
                (repo / name).write_bytes(data)
                names.append(name)
                total += len(data)
            subprocess.run(["/usr/bin/git", "add", "--", *names], cwd=repo, env=env, check=True)
            # Benchmark full-index scanning of an existing repo, not a bulk
            # addition which the publication policy now deliberately refuses.
            tree = subprocess.check_output(['/usr/bin/git', 'write-tree'], cwd=repo, env=env).strip()
            commit = subprocess.check_output(['/usr/bin/git', 'commit-tree', tree.decode(), '-m', 'fixture'],
                                             cwd=repo, env=env).strip()
            subprocess.run(['/usr/bin/git', 'update-ref', 'HEAD', commit.decode()], cwd=repo, env=env, check=True)
            with (repo / names[0]).open('ab') as stream:
                stream.write(b'ordinary update\n')
            subprocess.run(['/usr/bin/git', 'add', '--', names[0]], cwd=repo, env=env, check=True)
            started = time.monotonic()
            result = subprocess.run([str(bundle / "hooks/pre-commit")], cwd=repo, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=245)
            elapsed = time.monotonic() - started
            print(json.dumps({"runtime": args.runtime, "engine": args.engine, "files": count,
                              "changed_files": 1, "content_bytes": total + len(b'ordinary update\n'), "seconds": round(elapsed, 3),
                              "exit": result.returncode}), flush=True)
            if result.returncode != 0 or elapsed >= 120:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
