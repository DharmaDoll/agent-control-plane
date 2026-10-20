#!/usr/bin/env python3
"""Bounded Git object adapter; detection belongs to the pinned Gitleaks binary."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT.parent
RUNTIME = "native"
BINARY_SHA256 = "88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509"
MAX_BYTES = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_OBJECTS = 1000
MAX_INPUT = 65536
OID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
ARCHIVES = {".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".zst"}


class Rejected(Exception):
    """Only constant messages and internally generated object IDs may be used."""
    def __init__(self, reason: str, code: int = 2):
        self.reason, self.code = reason, code


def run(argv, *, data=None, cwd=None, env=None):
    try:
        return subprocess.run(argv, input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=15, cwd=cwd, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise Rejected("ERROR process unavailable or timed out") from None


def git(*args, data=None):
    # Preserve Git's index and receive-pack quarantine. Never apply replace refs.
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
               GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL="/dev/null")
    result = run(["/usr/bin/git", "--no-replace-objects", *args], data=data, env=env)
    if result.returncode:
        raise Rejected("ERROR Git input unavailable or invalid")
    return result.stdout


def oid(value: bytes) -> str:
    if not OID.fullmatch(value):
        raise Rejected("ERROR invalid object identity")
    return value.decode("ascii")


def bounded_read(stream, maximum=MAX_INPUT):
    value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise Rejected("INCOMPLETE input limit exceeded")
    return value


class Scanner:
    def __init__(self):
        self.binary = BUNDLE / "bin/gitleaks"
        if hashlib.sha256(self.binary.read_bytes()).hexdigest() != BINARY_SHA256:
            raise Rejected("ERROR scanner digest mismatch")
        self.docker = None
        manifest = BUNDLE / "docker-image.json"
        if RUNTIME == "docker":
            try:
                if manifest.is_symlink() or manifest.stat().st_size > 4096:
                    raise ValueError
                self.image = json.loads(manifest.read_bytes())["image_id"]
                spec = importlib.util.spec_from_file_location("docker_gitleaks", ROOT / "docker_gitleaks.py")
                self.docker = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.docker)
                self.docker.verify_image(self.image)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                raise Rejected("ERROR Docker runtime unavailable or invalid") from None
        self.total = 0

    def scan(self, value: bytes, label: str):
        self.total += len(value)
        if len(value) > MAX_BYTES or self.total > MAX_TOTAL:
            raise Rejected("INCOMPLETE content limit exceeded")
        try:
            text = value.decode("utf-8")
        except UnicodeError:
            raise Rejected("INCOMPLETE only UTF-8 text is supported") from None
        if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
            raise Rejected("INCOMPLETE binary or control characters")
        if b"version https://git-lfs.github.com/spec/v1" in value:
            raise Rejected("INCOMPLETE LFS content requires separate inspection")
        # Keep upstream MIME sniffing from silently skipping otherwise valid UTF-8 input.
        # The original bytes remain intact after a fixed non-secret text header.
        arguments = [
            "stdin", "--config", "/gitleaks.toml" if self.docker else str(BUNDLE / "gitleaks.toml"),
            "--gitleaks-ignore-path", "/dev/null", "--ignore-gitleaks-allow",
            "--redact=100", "--no-banner", "--no-color", "--log-level=error",
            "--max-decode-depth=0", "--max-archive-depth=0", "--timeout=10",
            "--exit-code=10", "--report-format=json", "--report-path=-",
        ]
        data = b"source002 text input\n" + value
        if self.docker:
            try:
                result = self.docker.scan(self.image, arguments, data)
            except RuntimeError:
                raise Rejected("ERROR Docker scan or cleanup incomplete") from None
        else:
            result = run([str(self.binary), *arguments], data=data, cwd=ROOT,
                         env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        # Neither stdout nor stderr is forwarded: even paths and error text may contain secrets.
        try:
            findings = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            raise Rejected("ERROR invalid scanner report") from None
        if not isinstance(findings, list):
            raise Rejected("ERROR invalid scanner report")
        if result.returncode == 0 and not findings:
            return
        if result.returncode == 10 and findings and all(
            isinstance(f, dict) and isinstance(f.get("RuleID"), str) for f in findings
        ):
            raise Rejected("REJECTED finding at " + label, 1)
        raise Rejected("ERROR scanner status/report disagreement or failure")


class Gate:
    def __init__(self, scanner):
        self.scanner = scanner
        self.seen = set()
        if git("rev-parse", "--is-shallow-repository").strip() != b"false":
            raise Rejected("INCOMPLETE shallow repository")
        # This example requires a fully materialized object database.
        config = git("config", "--local", "--list", "--name-only").lower().splitlines()
        if b"extensions.partialclone" in config or any(k.endswith(b".promisor") for k in config):
            raise Rejected("INCOMPLETE partial clone")

    def path(self, path: bytes):
        self.scanner.scan(path, "path metadata")
        if Path(path.decode("utf-8")).suffix.lower() in ARCHIVES:
            raise Rejected("INCOMPLETE archive format")

    def object(self, identity: str):
        if identity in self.seen:
            return []
        self.seen.add(identity)
        if len(self.seen) > MAX_OBJECTS:
            raise Rejected("INCOMPLETE object limit exceeded")
        size = int(git("cat-file", "-s", identity))
        if size > MAX_BYTES:
            raise Rejected("INCOMPLETE object size limit exceeded")
        kind = git("cat-file", "-t", identity).strip()
        if kind == b"tree":
            children = []
            listing = git("ls-tree", "-z", identity)
            for entry in listing.split(b"\0"):
                if not entry:
                    continue
                header, path = entry.split(b"\t", 1)
                mode, child_kind, child = header.split()
                if mode not in (b"100644", b"100755", b"040000"):
                    raise Rejected("INCOMPLETE symlink or submodule")
                expected_kind = b"tree" if mode == b"040000" else b"blob"
                if child_kind != expected_kind:
                    raise Rejected("ERROR inconsistent tree entry")
                self.path(path)
                children.append(oid(child))
            return children
        if kind not in (b"blob", b"commit", b"tag"):
            raise Rejected("INCOMPLETE unsupported object kind")
        content = git("cat-file", kind.decode(), identity)
        self.scanner.scan(content, kind.decode() + ":" + identity)
        if kind == b"blob":
            return []
        header = content.split(b"\n\n", 1)[0].splitlines()
        values = {}
        for line in header:
            if b" " not in line:
                continue
            key, value = line.split(b" ", 1)
            values.setdefault(key, []).append(value)
        if kind == b"commit":
            if len(values.get(b"tree", [])) != 1:
                raise Rejected("ERROR invalid commit object")
            return [oid(values[b"tree"][0])] + [oid(v) for v in values.get(b"parent", [])]
        if len(values.get(b"object", [])) != 1:
            raise Rejected("ERROR invalid tag object")
        return [oid(values[b"object"][0])]

    def walk(self, tips):
        queue = list(tips)
        while queue:
            queue.extend(self.object(queue.pop()))

    def staged(self):
        entries = git("ls-files", "--stage", "-z").split(b"\0")
        tips = []
        for entry in entries:
            if not entry:
                continue
            header, path = entry.split(b"\t", 1)
            mode, identity, stage = header.split()
            if stage != b"0" or mode not in (b"100644", b"100755"):
                raise Rejected("INCOMPLETE unmerged index, symlink or submodule")
            self.path(path)
            tips.append(oid(identity))
        self.walk(tips)

    def updates(self, raw, receive):
        tips = []
        for line in raw.splitlines():
            fields = line.split()
            if receive and len(fields) == 3:
                old, new, ref = fields
            elif not receive and len(fields) == 4:
                _local_ref, new, ref, old = fields
            else:
                raise Rejected("ERROR invalid hook input")
            oid(old)
            new_id = oid(new)
            if len(old) != len(new):
                raise Rejected("ERROR inconsistent object identity")
            self.scanner.scan(ref, "ref metadata")
            if not ref.startswith((b"refs/heads/", b"refs/tags/")):
                raise Rejected("INCOMPLETE unsupported ref namespace")
            if set(new) == {ord("0")}:
                continue
            tips.append(new_id)
        # Scan full reachability, including existing history. No remote-tracking trust.
        self.walk(tips)


def main():
    def timeout(_signum, _frame):
        raise Rejected("INCOMPLETE hook deadline exceeded")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        mode, *args = sys.argv[1:]
        gate = Gate(Scanner())
        if mode == "pre-commit" and not args:
            gate.staged()
        elif mode == "commit-msg" and len(args) == 1:
            with open(args[0], "rb") as message:
                gate.scanner.scan(bounded_read(message, MAX_BYTES), "commit message")
        elif mode in ("pre-push", "pre-receive"):
            gate.updates(bounded_read(sys.stdin.buffer), mode == "pre-receive")
        else:
            raise Rejected("ERROR invalid invocation")
        print("CHECKED no findings within the configured scope")
        return 0
    except Rejected as error:
        print(error.reason, file=sys.stderr)
        return error.code
    except (OSError, ValueError, IndexError, UnicodeError):
        print("ERROR input or trusted bundle unavailable", file=sys.stderr)
        return 2
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
