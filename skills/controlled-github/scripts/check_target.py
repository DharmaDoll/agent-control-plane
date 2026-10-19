#!/usr/bin/env python3
"""Read-only, local Git target check. Never print raw URLs or Git diagnostics."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


class Blocked(Exception):
    """Contains a fixed reason code, never external diagnostic text."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Blocked("INVALID_ARGUMENTS")


def git(root, *args, allow_missing=False):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=10, check=False,
    )
    if allow_missing and result.returncode == 1 and not result.stdout:
        return ""
    if result.returncode:
        raise Blocked("GIT_CHECK_FAILED")
    return result.stdout.decode("utf-8", errors="strict")


def repo_name(value):
    if value.endswith(".git"):
        value = value[:-4]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
        raise Blocked("UNSUPPORTED_REPOSITORY")
    return value


def parse_url(value):
    if not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise Blocked("UNSUPPORTED_URL")
    if any(c in value for c in "%\\?#"):
        raise Blocked("UNSUPPORTED_URL")
    if "://" not in value:
        match = re.fullmatch(r"git@([A-Za-z0-9.-]+):([^:]+)", value)
        if not match:
            raise Blocked("UNSUPPORTED_URL")
        return "ssh", match[1].lower(), repo_name(match[2])
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "ssh") or parsed.query or parsed.fragment:
        raise Blocked("UNSUPPORTED_URL")
    if parsed.password is not None or (parsed.scheme == "https" and parsed.username is not None):
        raise Blocked("EMBEDDED_CREDENTIALS")
    if parsed.scheme == "ssh" and parsed.username != "git":
        raise Blocked("UNSUPPORTED_URL")
    if parsed.port is not None or not parsed.hostname:
        raise Blocked("UNSUPPORTED_URL")
    authority = ("git@" if parsed.scheme == "ssh" else "") + parsed.hostname
    if parsed.netloc.lower() != authority:
        raise Blocked("UNSUPPORTED_URL")
    if not parsed.path.startswith("/"):
        raise Blocked("UNSUPPORTED_URL")
    return parsed.scheme, parsed.hostname.lower(), repo_name(parsed.path[1:])


def check(args):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", args.remote):
        raise Blocked("INVALID_ARGUMENTS")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", args.host):
        raise Blocked("INVALID_ARGUMENTS")
    expected = (args.transport, args.host.lower(), repo_name(args.repo))
    # Do not silently remove overrides: subsequent Git commands might use them.
    if any(name in os.environ for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
    )):
        raise Blocked("GIT_ENV_OVERRIDE")
    root = Path(args.root).resolve(strict=True)
    actual = Path(git(root, "rev-parse", "--show-toplevel").removesuffix("\n")).resolve(strict=True)
    if root != actual:
        raise Blocked("ROOT_MISMATCH")
    # Inspect configured values before Git normalizes or rewrites them. NUL
    # delimiters preserve embedded line breaks without exposing the values.
    for key in ("url", "pushurl"):
        raw = git(root, "config", "--null", "--get-all", f"remote.{args.remote}.{key}", allow_missing=True)
        values = raw.removesuffix("\0").split("\0") if raw else []
        if len(values) > 1:
            raise Blocked("MULTIPLE_OR_MISSING_URLS")
        for value in values:
            if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
                raise Blocked("UNSUPPORTED_URL")
            if value.startswith(("https://", "ssh://")):
                parse_url(value)
    mirror = git(root, "config", "--bool", "--get-all", f"remote.{args.remote}.mirror", allow_missing=True)
    if any(line != "false" for line in mirror.splitlines()):
        raise Blocked("MIRROR_REMOTE")
    fetch = git(root, "remote", "get-url", "--all", args.remote).removesuffix("\n").split("\n")
    push = git(root, "remote", "get-url", "--push", "--all", args.remote).removesuffix("\n").split("\n")
    if len(fetch) != 1 or len(push) != 1:
        raise Blocked("MULTIPLE_OR_MISSING_URLS")
    # get-url expands insteadOf and pushInsteadOf using Git's own rules.
    fetch_target, push_target = parse_url(fetch[0]), parse_url(push[0])
    if fetch_target != push_target:
        raise Blocked("FETCH_PUSH_MISMATCH")
    if fetch_target != expected:
        raise Blocked("TARGET_MISMATCH")
    return {"status": "PASS", "reason": "LOCAL_TARGET_MATCH", "target": {
        "host": expected[1], "repo": expected[2], "transport": expected[0],
    }}


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    for name in ("root", "remote", "host", "repo"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--transport", choices=("https", "ssh"), required=True)
    try:
        result = check(parser.parse_args(argv))
    except Blocked as exc:
        result = {"status": "BLOCKED", "reason": str(exc)}
    except subprocess.TimeoutExpired:
        result = {"status": "BLOCKED", "reason": "GIT_TIMEOUT"}
    except (OSError, ValueError, RuntimeError):
        result = {"status": "BLOCKED", "reason": "CHECK_UNAVAILABLE"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
