#!/usr/bin/env python3
"""Small standard-library secret pattern scanner for local Git hooks."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import signal
from urllib.parse import unquote_to_bytes

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
        rb"(?i)\b(?<!-)(?:aws_)?secret_access_key['\"]?\s*[:=]\s*['\"]?"
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
        rb"(?im)^[\t ]*//[^\s=]+/:_(?:authToken|auth|password)\s*=\s*"
        rb"['\"]?[A-Za-z0-9+/=_-]{20,}"
    ),
    "pypi-api-token": rb"\bpypi-[A-Za-z0-9_-]{85,}\b",
    "credential-assignment": (
        rb"(?i)\b(?<!-)(?:api[_-]?key|client[_-]?secret|password|token|"
        rb"access[_-]?token|refresh[_-]?token|auth[_-]?token|"
        rb"private[_-]?token|webhook[_-]?secret|signing[_-]?secret)"
        rb"['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9/+_.-]{12,}"
    ),
    "openai-token": rb"\bsk-(?:(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,200}|[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20})(?![\w-])",
    "anthropic-token": rb"\bsk-ant-(?:api03|admin01)-[A-Za-z0-9_-]{93}AA(?![\w-])",
    "huggingface-token": rb"\b(?:hf_|api_org_)[A-Za-z]{34}(?![\w-])",
    "gitlab-token": rb"\b(?:glpat-|gldt-|glrt-|glrtr-)[A-Za-z0-9_-]{20,300}(?:\.[a-z0-9]{9})?(?![\w.-])",
    "npm-token": rb"\bnpm_[A-Za-z0-9]{36}(?![\w-])",
    "dockerhub-token": rb"\bdckr_pat_[A-Za-z0-9_-]{27,128}(?![\w-])",
    "vercel-token": rb"\bvc[piark]_[A-Za-z0-9_-]{24,200}(?![\w-])",
    "supabase-secret": rb"\bsb_secret_[A-Za-z0-9_-]{20,200}(?![\w-])",
    "digitalocean-token": rb"\bdo[opr]_v1_[a-f0-9]{64}(?![\w-])",
    "slack-token": rb"\b(?:xox[bpars]-[A-Za-z0-9-]{20,200}|xapp-[0-9]-[A-Z0-9]+-[0-9]+-[a-z0-9]+)(?![\w-])",
    "discord-webhook": rb"https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api(?:/v[0-9]+)?/webhooks/[0-9]{17,20}/[A-Za-z0-9_-]{50,100}(?![\w-])",
    "notion-token": rb"\bntn_[A-Za-z0-9]{46,80}(?![\w-])",
    "atlassian-token": rb"\bATATT3[A-Za-z0-9_=-]{186}(?![\w=-])",
    "linear-token": rb"\blin_api_[A-Za-z0-9]{40}(?![\w-])",
    "stripe-secret": rb"\b(?:[sr]k_(?:live|test|prod)_[A-Za-z0-9]{10,200}|whsec_[A-Za-z0-9]{20,200})(?![\w-])",
    "sendgrid-token": rb"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}(?![\w-])",
    "resend-token": rb"\bre_[A-Za-z0-9_]{32,100}(?![\w-])",
    "grafana-token": rb"\b(?:glsa_[A-Za-z0-9]{32}_[a-f0-9]{8}|glc_[A-Za-z0-9+/=_-]{32,400})(?![\w/+=-])",
    "vault-token": rb"\bhv[bs]\.[A-Za-z0-9_-]{24,300}(?![\w-])",
    "azure-sas-url": rb"https://[A-Za-z0-9.-]+\.(?:blob|file|queue|table)\.core\.windows\.net/[^\s\"'<>]{0,4096}[?&]sig=[A-Za-z0-9%/+_-]{20,}(?:=|%3[Dd])?",
}
COMPILED_RULES = {
    name: re.compile(pattern) for name, pattern in SECRET_RULES.items()
}

# Opaque credentials need a specific field name, never just a service name in
# nearby prose. Values and names are ASCII/case-sensitive and insensitive,
# respectively. This is lexical detection, not a language parser.
CONTEXT_RULES = {
    "ai-key-assignment": ("openai_api_key anthropic_api_key huggingface_token hf_token", rb"[A-Za-z0-9_./+=~-]{20,512}"),
    "cloudflare-credential": ("cloudflare_api_token cloudflare_api_key cf_api_token cf_api_key", rb"[A-Za-z0-9_-]{37,40}"),
    "azure-credential": ("azure_client_secret azure_storage_key accountkey", rb"[A-Za-z0-9_./+=~-]{32,128}"),
    "azure-sas": ("azure_storage_sas_token sharedaccesssignature", rb"[^\s'\"]{20,4096}"),
    "netlify-token": ("netlify_auth_token netlify_api_token", rb"[A-Za-z0-9_=-]{40,128}"),
    "vercel-token-assignment": ("vercel_token vercel_api_token", rb"[A-Za-z0-9_-]{24,200}"),
    "supabase-service-role": ("supabase_service_role_key service_role_key", rb"[A-Za-z0-9_.-]{20,512}"),
    "discord-token": ("discord_token discord_bot_token discord_client_secret", rb"[A-Za-z0-9_.-]{32,200}"),
    "notion-token-assignment": ("notion_token notion_api_key notion_secret", rb"(?:secret_|ntn_)[A-Za-z0-9]{32,80}"),
    "atlassian-token-assignment": ("atlassian_api_token jira_api_token confluence_api_token", rb"[A-Za-z0-9_=-]{24,256}"),
    "datadog-api-key": ("dd_api_key datadog_api_key", rb"[a-fA-F0-9]{32}"),
    "datadog-app-key": ("dd_app_key dd_application_key datadog_app_key datadog_application_key", rb"[a-fA-F0-9]{40}"),
    "grafana-token-assignment": ("grafana_api_key grafana_token", rb"[A-Za-z0-9_./+=-]{32,512}"),
    "vault-token-assignment": ("vault_token", rb"(?:s\.[A-Za-z0-9]{24}|hv[bs]\.[A-Za-z0-9_-]{24,300})"),
}
CONTEXT_KEYS = {key.encode(): name for name, (keys, _) in CONTEXT_RULES.items()
                for key in keys.split()}
CONTEXT_VALUES = {name: re.compile(value) for name, (_, value) in CONTEXT_RULES.items()}
CONTEXT_ASSIGNMENT = re.compile(
    rb"(?i)\b(?<!-)(" + b"|".join(map(re.escape, CONTEXT_KEYS)) +
    rb")[\"']?\s*[:=]\s*[\"']?([^\s\"',;{}]{1,4097})"
)
BASIC_HEADER = re.compile(
    rb"(?i)\b(?<!-)(?:proxy-)?authorization[\"']?\s*[:=]\s*[\"']?"
    rb"Basic[\t ]+([^\s\"',;<>]{1,4097})"
)
URL_AUTHORITY = re.compile(
    rb"(?i)\b(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|rediss?)://"
    rb"([^\s/\"'<>?#]+)"
)
VARIABLE = re.compile(rb"(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)\Z")


def matching_rules(content: bytes) -> set[str]:
    """Inspect one byte string without returning or logging matched material."""
    found = {name for name, pattern in COMPILED_RULES.items() if pattern.search(content)}
    for match in CONTEXT_ASSIGNMENT.finditer(content):
        name = CONTEXT_KEYS[match[1].lower()]
        if CONTEXT_VALUES[name].fullmatch(match[2]):
            found.add(name)
    for match in BASIC_HEADER.finditer(content):
        encoded = match[1]
        if len(encoded) > 4096:
            raise ScanError("credential candidate exceeds limit")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            continue
        _user, separator, decoded_password = decoded.partition(b":")
        if separator and decoded_password and not VARIABLE.fullmatch(decoded_password):
            found.add("basic-auth")
    for match in URL_AUTHORITY.finditer(content):
        authority = match[1]
        userinfo, separator, host = authority.rpartition(b"@")
        if not separator or not host:
            continue
        if len(authority) > 4096:
            raise ScanError("credential candidate exceeds limit")
        _user, separator, raw_password = userinfo.partition(b":")
        decoded_password = unquote_to_bytes(raw_password)
        if separator and decoded_password and not VARIABLE.fullmatch(decoded_password):
            found.add("credential-url")
    return found


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
    if file_content and IMAGES.allow(label, content):
        # Preserve name policy and secret-like name checks, not raster contents.
        findings = [("sensitive-filename", label)] if blocked_path(label) else []
        findings.extend((name, label) for name in sorted(matching_rules(
            label.encode('utf-8', errors='surrogateescape'))))
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
    for name in sorted(matching_rules(content) | matching_rules(
            label.encode("utf-8", errors="surrogateescape"))):
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
        if matching_rules(remote_ref.encode()):
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
