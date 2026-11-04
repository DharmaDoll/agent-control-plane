#!/usr/bin/env python3
"""Report gh credential storage without disclosing credentials or raw diagnostics."""

import argparse
import json
import os
import re
import subprocess


MAX_OUTPUT = 128 * 1024
MAX_ACCOUNTS = 128
TIMEOUT = 20
# gh's built-in jq implementation projects metadata before stdout is captured.
# Never request --show-token, raw diagnostics, scopes, or credential values.
METADATA_QUERY = (
    '{hosts: (.hosts | with_entries(.value |= '
    'map({host, login, active, state, tokenSource})))}'
)


class Blocked(Exception):
    """Fixed reason code only, never external diagnostic text."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Blocked("INVALID_ARGUMENTS")


def classify_source(source):
    """Classify only metadata reported by gh, never open the reported path."""
    if not isinstance(source, str) or len(source) > 4096 or not source.isprintable():
        return "UNKNOWN"
    if source == "keyring":
        return "KEYRING"
    if source in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        return "ENVIRONMENT"
    if source == "oauth_token" or source.replace("\\", "/").split("/")[-1] == "hosts.yml":
        return "PLAINTEXT"
    return "UNKNOWN"


def result(status, reason, authentication="NOT_VERIFIED", storage="UNKNOWN", warnings=()):
    return dict(status=status, reason=reason, authentication=authentication,
                active_storage=storage, warnings=list(warnings))


def assess(payload, host, account):
    """Validate gh metadata and separate authentication from storage warnings."""
    if not isinstance(payload, dict) or not isinstance(payload.get("hosts"), dict):
        raise Blocked("UNSUPPORTED_GH_OUTPUT")
    hosts = payload["hosts"]
    if not hosts:
        return result("BLOCKED", "NOT_AUTHENTICATED", "FAIL")
    if set(hosts) != {host}:
        raise Blocked("UNEXPECTED_HOST")
    entries = hosts[host]
    if not isinstance(entries, list) or len(entries) > MAX_ACCOUNTS:
        raise Blocked("UNSUPPORTED_GH_OUTPUT")
    if not entries:
        return result("BLOCKED", "NOT_AUTHENTICATED", "FAIL")
    for entry in entries:
        if (not isinstance(entry, dict) or entry.get("host") != host
                or type(entry.get("active")) is not bool
                or entry.get("state") not in ("success", "error", "timeout")
                or not isinstance(entry.get("login"), str)
                or len(entry["login"]) > 256):
            raise Blocked("UNSUPPORTED_GH_OUTPUT")
    sources = [classify_source(entry.get("tokenSource")) for entry in entries]
    warnings = []
    for source, warning in (("PLAINTEXT", "PLAINTEXT_CREDENTIAL_STORAGE"),
                            ("ENVIRONMENT", "ENVIRONMENT_STORAGE_NOT_VERIFIED"),
                            ("UNKNOWN", "CREDENTIAL_STORAGE_UNKNOWN")):
        if source in sources:
            warnings.append(warning)
    active = [i for i, entry in enumerate(entries) if entry["active"]]
    if len(active) != 1:
        return result("BLOCKED", "ACTIVE_ACCOUNT_AMBIGUOUS", warnings=warnings)
    index = active[0]
    entry, storage = entries[index], sources[index]
    if entry["state"] != "success":
        reason = "AUTH_TIMEOUT" if entry["state"] == "timeout" else "AUTH_CHECK_FAILED"
        return result("BLOCKED", reason, "FAIL", storage, warnings)
    if entry["login"].casefold() != account.casefold():
        return result("BLOCKED", "ACCOUNT_MISMATCH", "FAIL", storage, warnings)
    return result("WARN" if warnings else "PASS", "AUTHENTICATED", "PASS", storage, warnings)


def read_metadata(host):
    # Preserve the approved auth/config path. Suppress debugging and prompts only
    # in this child; never read token env values or persist configuration changes.
    environment = os.environ.copy()
    environment.pop("GH_DEBUG", None)
    environment.pop("DEBUG", None)
    environment.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1",
                       GH_NO_EXTENSION_UPDATE_NOTIFIER="1", GH_TELEMETRY="0")
    completed = subprocess.run(
        ["gh", "auth", "status", "--hostname", host, "--json", "hosts",
         "--jq", METADATA_QUERY],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=TIMEOUT, check=False, env=environment,
    )
    if completed.returncode:
        raise Blocked("GH_CHECK_FAILED")
    # gh is trusted. This parser limit is checked after capture, not an OS memory limit.
    if len(completed.stdout) > MAX_OUTPUT:
        raise Blocked("GH_OUTPUT_TOO_LARGE")
    try:
        return json.loads(completed.stdout)
    except (ValueError, RecursionError):
        raise Blocked("UNSUPPORTED_GH_OUTPUT") from None


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--host", required=True)
    parser.add_argument("--account", required=True)
    try:
        args = parser.parse_args(argv)
        if (len(args.host) > 253
                or not re.fullmatch(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", args.host)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}(?:\[bot\])?", args.account)):
            raise Blocked("INVALID_ARGUMENTS")
        host = args.host.lower()
        report = assess(read_metadata(host), host, args.account)
    except Blocked as exc:
        report = result("BLOCKED", str(exc))
    except subprocess.TimeoutExpired:
        report = result("BLOCKED", "GH_TIMEOUT")
    except (OSError, ValueError):
        report = result("BLOCKED", "CHECK_UNAVAILABLE")
    print(json.dumps(report, sort_keys=True))
    return {"PASS": 0, "WARN": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
