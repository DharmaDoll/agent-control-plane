#!/usr/bin/env python3
"""Small standard-library secret pattern scanner for local Git hooks."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import signal

# -I omits the script directory. Add only the reviewed bundle's module directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publication_policy as policy

IMAGES = policy.Images()


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 1000
MAX_HOOK_BYTES = 65536
OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_total = 0
_items = 0
ZERO_OID = re.compile(r"^0+$")
# Refuse standalone pointer metadata, including legacy headers and truncated
# pointers. A quoted occurrence in source is ordinary text, not an exemption.
LFS_HEADER = re.compile(
    r"(?m)^[\t ]*version[\t ]+(?:https://git-lfs\.github\.com/spec/v1|"
    r"https://hawser\.github\.com/spec/v1|http://git-media\.io/v/2)[\t ]*\r?$"
)

BLOCKED_NAMES = {
    ".ds_store",
    ".netrc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "thumbs.db",
}
BLOCKED_SUFFIXES = {
    ".7z", ".bin", ".class", ".db", ".dll", ".dylib", ".exe", ".gz",
    ".jar", ".jks", ".key", ".keystore", ".mdb", ".msi", ".p12",
    ".pem", ".pfx", ".pyc", ".pyo", ".rar", ".so", ".sqlite",
    ".sqlite3", ".tar", ".war", ".zip",
}
ALLOWED_ENV_ENDINGS = (".example", ".sample", ".template")

SECRET_RULES = {
    "private-key": rb"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----",
    "github-token": rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    "github-fine-grained-pat": rb"\bgithub_pat_[A-Za-z0-9_]{82}\b",
    "aws-access-key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "aws-secret-access-key": (
        rb"(?im)^\s*(?:aws_)?secret_access_key\s*[:=]\s*['\"]?"
        rb"[A-Za-z0-9/+=]{40}(?=$|[\s'\"])"
    ),
    "google-api-key": rb"\bAIza[0-9A-Za-z_-]{35}\b",
    "jwt": (
        rb"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\."
        rb"[A-Za-z0-9_-]{5,}\b"
    ),
    "bearer-token": rb"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}",
    "slack-webhook": (
        rb"https://hooks\.slack\.com/services/[A-Za-z0-9]{8,}/"
        rb"[A-Za-z0-9]{8,}/[A-Za-z0-9]{16,}"
    ),
    "npmrc-auth-token": (
        rb"(?im)^\s*//[^\s=]+/:_(?:authToken|auth|password)\s*=\s*"
        rb"['\"]?[A-Za-z0-9+/=_-]{20,}"
    ),
    "pypi-api-token": rb"\bpypi-[A-Za-z0-9_-]{85,}\b",
    "credential-assignment": (
        rb"(?im)^\s*(?:api[_-]?key|client[_-]?secret|password|token|"
        rb"access[_-]?token|refresh[_-]?token|auth[_-]?token|"
        rb"private[_-]?token|webhook[_-]?secret|signing[_-]?secret)"
        rb"\s*[:=]\s*['\"]?[A-Za-z0-9/+_.-]{12,}"
    ),
}
COMPILED_RULES = {
    name: re.compile(pattern) for name, pattern in SECRET_RULES.items()
}


class ScanError(RuntimeError):
    """The scanner could not produce a result."""


class MetadataFinding(ScanError):
    """A secret-like ref name was detected; never print that name."""


def git(*arguments: str) -> bytes:
    """Run Git and return stdout, or stop when the input cannot be inspected."""
    try:
        result = subprocess.run(
            ["/usr/bin/git", "--no-replace-objects", *arguments],
            env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
                     GIT_TERMINAL_PROMPT="0"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ScanError("Git unavailable or timed out") from None
    if result.returncode != 0:
        raise ScanError("Git input unavailable or invalid")
    if len(result.stdout) > MAX_TOTAL_BYTES:
        raise ScanError("Git output limit exceeded")
    return result.stdout


def blocked_path(path: str) -> bool:
    """Return True for file types this text-only example does not inspect."""
    name = PurePosixPath(path).name.lower()
    if name == ".env" or name.startswith(".env."):
        return not name.endswith(ALLOWED_ENV_ENDINGS)
    return name in BLOCKED_NAMES or PurePosixPath(name).suffix in BLOCKED_SUFFIXES


def scan(label: str, content: bytes, *, file_content: bool = False) -> list[tuple[str, str]]:
    """Return rule names and locations without returning matched values."""
    global _total, _items
    _items += 1
    if _items > MAX_ITEMS:
        raise ScanError("scan budget exceeded")
    if len(content) > MAX_FILE_BYTES:
        raise ScanError("file exceeds scan limit")
    if file_content and IMAGES.validate(label, content):
        # Preserve name policy and secret-like name checks, not raster contents.
        findings = [("sensitive-filename", label)] if blocked_path(label) else []
        findings.extend((name, label) for name, pattern in COMPILED_RULES.items()
                        if pattern.search(label.encode('utf-8', errors='surrogateescape')))
        return findings
    _total += len(content)
    if _total > MAX_TOTAL_BYTES:
        raise ScanError("scan budget exceeded")
    if b"\0" in content:
        raise ScanError("NUL-containing input cannot be scanned")
    if LFS_HEADER.search(content.decode("utf-8", errors="replace").strip()):
        raise ScanError("LFS content requires separate inspection")

    findings: list[tuple[str, str]] = []
    if blocked_path(label):
        findings.append(("sensitive-filename", label))
    for name, pattern in COMPILED_RULES.items():
        if pattern.search(content) or pattern.search(label.encode("utf-8", errors="surrogateescape")):
            findings.append((name, label))
    return findings


def decode_paths(raw: bytes) -> list[str]:
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw.split(b"\0")
        if item
    ]


def scan_staged() -> list[tuple[str, str]]:
    validate_repository()
    policy.check_staged()
    validate_entries(git("ls-files", "--stage", "-z"), staged=True)
    findings: list[tuple[str, str]] = []
    paths = decode_paths(
        git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    )
    for path in paths:
        findings.extend(scan(path, read_object(f":{path}"), file_content=True))
    return findings


def scan_commit(commit: str) -> list[tuple[str, str]]:
    if not OID.fullmatch(commit):
        raise ScanError("invalid commit identity")
    validate_entries(git("ls-tree", "-r", "-z", commit), staged=False)
    short = commit[:12]
    findings = scan(
        f"{short}:commit-message",
        git("show", "-s", "--format=%B", commit),
    )
    paths = decode_paths(
        git(
            "diff-tree", "--root", "-m", "--no-commit-id", "--name-only",
            "--diff-filter=ACMR", "-r", "-z", commit,
        )
    )
    # A merge can report the same path against several parents.
    for path in dict.fromkeys(paths):
        for rule, _label in scan(path, read_object(f"{commit}:{path}"), file_content=True):
            findings.append((rule, f"{short}:{path}"))
    return findings


def introduced_commits() -> list[str]:
    """Read pre-push stdin and return commits introduced by the updates."""
    commits: list[str] = []
    raw = sys.stdin.buffer.read(MAX_HOOK_BYTES + 1)
    if len(raw) > MAX_HOOK_BYTES:
        raise ScanError("hook input limit exceeded")
    policy.check_updates(raw)
    for line in raw.decode("utf-8").splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ScanError("invalid pre-push input")
        local_ref, local_oid, remote_ref, remote_oid = fields
        if not OID.fullmatch(local_oid) or not OID.fullmatch(remote_oid) or len(local_oid) != len(remote_oid):
            raise ScanError("invalid object identity")
        if not remote_ref.startswith("refs/heads/"):
            raise ScanError("only branch updates are supported by the Python scanner")
        # Ref names are metadata too; never echo them.
        if any(pattern.search(remote_ref.encode()) for pattern in COMPILED_RULES.values()):
            raise MetadataFinding("sensitive ref metadata")
        if ZERO_OID.fullmatch(local_oid):
            continue
        if git("cat-file", "-t", local_oid).strip() != b"commit":
            raise ScanError("only commit tips are supported by the Python scanner")
        if ZERO_OID.fullmatch(remote_oid):
            revision = ("rev-list", local_oid)
        else:
            revision = ("rev-list", f"{remote_oid}..{local_oid}")
        commits.extend(git(*revision).decode("ascii").splitlines())
        if len(commits) > MAX_ITEMS:
            raise ScanError("commit limit exceeded")
    return list(dict.fromkeys(commits))


def scan_history() -> list[tuple[str, str]]:
    validate_repository()
    findings: list[tuple[str, str]] = []
    for commit in introduced_commits():
        findings.extend(scan_commit(commit))
    return findings


def report(findings: list[tuple[str, str]]) -> int:
    IMAGES.report()
    for rule, label in findings:
        location = hashlib.sha256(label.encode("utf-8", errors="surrogateescape")).hexdigest()[:16]
        print(f"BLOCK {rule} location:{location}")
    if findings:
        print(f"REJECTED {len(findings)} finding(s); matched values suppressed")
        return 1
    print("CHECKED no findings within the configured scope")
    return 0


def main() -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ScanError("invalid invocation")

    parser = Parser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--pre-push", action="store_true")
    mode.add_argument("--file", type=Path)
    parser.add_argument("--label")
    args = parser.parse_args()

    try:
        if args.staged:
            findings = scan_staged()
        elif args.pre_push:
            findings = scan_history()
        else:
            if args.file is None or not args.label:
                raise ScanError("--file requires --label")
            with args.file.open("rb") as stream:
                findings = scan(args.label, stream.read(MAX_FILE_BYTES + 1))
    except policy.PolicyError as error:
        print(f"ERROR policy {error}", file=sys.stderr)
        return 2
    except MetadataFinding:
        print("REJECTED secret-like ref metadata", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, ScanError):
        print("ERROR input unavailable, unsupported, or scan incomplete", file=sys.stderr)
        return 2
    return report(findings)


def validate_repository() -> None:
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ScanError("shallow history is unsupported")
    keys = git("config", "--local", "--list", "--name-only").lower().splitlines()
    if b"extensions.partialclone" in keys or any(k.endswith(b".promisor") for k in keys):
        raise ScanError("partial clone is unsupported")


def validate_entries(raw: bytes, *, staged: bool) -> None:
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        header, _path = entry.split(b"\t", 1)
        mode, _identity, kind = header.split()
        if mode not in (b"100644", b"100755") or (staged and kind != b"0"):
            raise ScanError("unmerged index, symlink or submodule is unsupported")


def read_object(spec: str) -> bytes:
    if int(git("cat-file", "-s", spec)) > MAX_FILE_BYTES:
        raise ScanError("object size limit exceeded")
    return git("cat-file", "blob", spec)


if __name__ == "__main__":
    def deadline(_signum, _frame):
        raise ScanError("hook deadline exceeded")
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(120)
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ScanError):
        print("ERROR input unavailable, unsupported, or scan incomplete", file=sys.stderr)
        raise SystemExit(2)
