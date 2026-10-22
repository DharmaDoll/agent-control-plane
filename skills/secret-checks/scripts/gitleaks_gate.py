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
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_policy as policy

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT.parent
RUNTIME = "native"
BINARY_SHA256 = "13483d25dc5c1f110b35e8f70aca21e0fa6aec1783d4fc406d2ea186d005982e"
MAX_BYTES = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_OBJECTS = 1000
MAX_INPUT = 65536
MAX_WIRE = 64 * 1024 * 1024
OID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
ARCHIVES = {".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".zst"}
LFS_HEADER = re.compile(
    r"(?m)^[\t ]*version[\t ]+(?:https://git-lfs\.github\.com/spec/v1|"
    r"https://hawser\.github\.com/spec/v1|http://git-media\.io/v/2)[\t ]*\r?$"
)


class Rejected(Exception):
    """Only constant messages and internally generated object IDs may be used."""
    def __init__(self, reason: str, code: int = 2):
        self.reason, self.code = reason, code


def run(argv, *, data=None, cwd=None, env=None, timeout=15):
    try:
        return subprocess.run(argv, input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout, cwd=cwd, env=env)
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
    def __init__(self, deadline=None):
        self.deadline = deadline if deadline is not None else time.monotonic() + 120
        self.binary = BUNDLE / "bin/gitleaks-runner"
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
        self.inputs = []

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
        if LFS_HEADER.search(text.strip()):
            raise Rejected("INCOMPLETE LFS content requires separate inspection")
        if self.total + 16 + (len(self.inputs) + 1) * 8 > MAX_WIRE:
            raise Rejected("INCOMPLETE transport limit exceeded")
        self.inputs.append(value)

    def finish(self):
        arguments = ["--config", "/gitleaks.toml" if self.docker else str(BUNDLE / "gitleaks.toml")]
        data = bytearray(struct.pack(">4sIQ", b"SCB1", len(self.inputs), self.total))
        for sequence, value in enumerate(self.inputs):
            data.extend(struct.pack(">II", sequence, len(value)))
            data.extend(value)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Rejected("INCOMPLETE hook deadline exceeded")
        if self.docker:
            try:
                result = self.docker.scan(self.image, arguments, data, deadline=self.deadline)
            except RuntimeError:
                raise Rejected("ERROR Docker scan or cleanup incomplete") from None
        else:
            result = run([str(self.binary), *arguments], data=data, cwd=ROOT,
                         env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "GOTRACEBACK": "none"},
                         timeout=remaining)
        # Neither stdout nor stderr is forwarded: even paths and error text may contain secrets.
        try:
            if len(result.stdout) > 4 * 1024 * 1024:
                raise ValueError
            report = json.loads(result.stdout)
            if (not isinstance(report, dict)
                    or set(report) != {"version", "complete", "processed", "bytes", "findings"}
                    or type(report["version"]) is not int or report["version"] != 1
                    or report["complete"] is not True
                    or type(report["processed"]) is not int or report["processed"] != len(self.inputs)
                    or type(report["bytes"]) is not int or report["bytes"] != self.total
                    or not isinstance(report["findings"], list)):
                raise ValueError
            findings = report["findings"]
            seen = set()
            for finding in findings:
                if (not isinstance(finding, dict) or set(finding) != {"input", "rules"}
                        or type(finding["input"]) is not int
                        or not 0 <= finding["input"] < len(self.inputs)
                        or finding["input"] in seen or not isinstance(finding["rules"], list)
                        or not finding["rules"] or any(not isinstance(rule, str)
                            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", rule) for rule in finding["rules"])):
                    raise ValueError
                seen.add(finding["input"])
        except (ValueError, UnicodeError, KeyError, TypeError):
            raise Rejected("ERROR invalid scanner report") from None
        if result.returncode == 0 and not findings:
            return
        if result.returncode == 10 and findings:
            raise Rejected("REJECTED finding in batch", 1)
        raise Rejected("ERROR scanner status/report disagreement or failure")


class Gate:
    def __init__(self, scanner):
        self.scanner = scanner
        self.seen = set()
        self.images = policy.Images()
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

    def object(self, identity: str, path: bytes | None = None):
        # Validate every extension context, even when the same blob is reused.
        name = path.decode('utf-8') if path is not None else None
        image_kind = policy.image_format(name) if name is not None else None
        key = (identity, image_kind)
        if key in self.seen:
            return []
        self.seen.add(key)
        if len(self.seen) > MAX_OBJECTS:
            raise Rejected("INCOMPLETE object limit exceeded")
        size = int(git("cat-file", "-s", identity))
        if size > (policy.IMAGE_BYTES if image_kind else MAX_BYTES):
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
                children.append((oid(child), path if child_kind == b'blob' else None))
            return children
        if kind not in (b"blob", b"commit", b"tag"):
            raise Rejected("INCOMPLETE unsupported object kind")
        content = git("cat-file", kind.decode(), identity)
        if kind == b'blob' and name is not None and self.images.validate(name, content):
            return []
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
            return [(oid(values[b"tree"][0]), None)] + [(oid(v), None) for v in values.get(b"parent", [])]
        if len(values.get(b"object", [])) != 1:
            raise Rejected("ERROR invalid tag object")
        return [(oid(values[b"object"][0]), None)]

    def walk(self, tips):
        queue = list(tips)
        while queue:
            queue.extend(self.object(*queue.pop()))

    def staged(self):
        policy.check_staged()
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
            tips.append((oid(identity), path))
        self.walk(tips)

    def updates(self, raw, receive):
        policy.check_updates(raw, receive=receive)
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
            tips.append((new_id, None))
        # Scan full reachability, including existing history. No remote-tracking trust.
        self.walk(tips)


def main():
    def timeout(_signum, _frame):
        raise Rejected("INCOMPLETE hook deadline exceeded")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        mode, *args = sys.argv[1:]
        gate = Gate(Scanner(time.monotonic() + 120))
        if mode == "pre-commit" and not args:
            gate.staged()
        elif mode == "commit-msg" and len(args) == 1:
            with open(args[0], "rb") as message:
                gate.scanner.scan(bounded_read(message, MAX_BYTES), "commit message")
        elif mode in ("pre-push", "pre-receive"):
            gate.updates(bounded_read(sys.stdin.buffer), mode == "pre-receive")
        else:
            raise Rejected("ERROR invalid invocation")
        gate.scanner.finish()
        gate.images.report()
        print("CHECKED no findings within the configured scope")
        return 0
    except policy.PolicyError as error:
        print(f"ERROR policy {error}", file=sys.stderr)
        return 2
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
