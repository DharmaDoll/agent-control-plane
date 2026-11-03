#!/usr/bin/env python3
"""Generate offline Claude Code settings candidates; never activate a policy."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys


VERSION = "2"
MAX_BYTES = 1024 * 1024
RESERVED_NAMES = {"settings.json", "settings.local.json", "managed-settings.json", ".mcp.json"}
RESERVED_DIRECTORIES = {".claude", "managed-settings.d"}
# Fixed recommendations, not arbitrary settings overlays or inferred grants.
SAMPLES = {
    "code-review": {
        "mode": "review",
        "summary": "Read source files without editing, shell execution or delegation.",
        "additional_domains": (),
        "limitations": ("No shell-based inspection or test execution.",
                        "No new network grants; inherited grants still require review."),
    },
    "local-development": {
        "mode": "development",
        "summary": "Edit and test locally with dependencies already available.",
        "additional_domains": (),
        "limitations": ("No dependency downloads are pre-approved by this sample.",
                        "No new network grants; inherited grants still require review."),
    },
    "npm-dependencies": {
        "mode": "development",
        "summary": "Develop with explicitly requested public npm dependency retrieval.",
        "additional_domains": ("registry.npmjs.org",),
        "limitations": ("Host access is not limited to downloads or approved packages.",
                        "Private registries and external install-script downloads are not covered.",
                        "Home .npmrc remains protected; do not bypass its deny."),
    },
    "pypi-dependencies": {
        "mode": "development",
        "summary": "Develop with explicitly requested public PyPI dependency retrieval.",
        "additional_domains": ("pypi.org", "files.pythonhosted.org"),
        "limitations": ("Host access is not limited to downloads or approved packages.",
                        "Private indexes, VCS dependencies and external build downloads are not covered.",
                        "Credential protections remain enabled."),
    },
}
MODE_SAMPLES = {"review": "code-review", "development": "local-development"}
# The paths are a default-location catalogue, not authentication discovery.
CREDENTIAL_DIRS = (
    ".ssh", ".aws", ".config/gcloud", ".azure", ".oci", ".kube", ".gnupg",
)
CREDENTIAL_FILES = (
    ".docker/config.json", ".config/containers/auth.json",
    ".terraform.d/credentials.tfrc.json", ".terraformrc",
    ".pulumi/credentials.json", ".vault-token", ".config/gh/hosts.yml",
    ".config/glab-cli/config.yml", ".git-credentials", ".config/git/credentials",
    ".npmrc", ".pypirc", ".netrc", ".cargo/credentials",
    ".cargo/credentials.toml", ".gem/credentials", ".pgpass", ".my.cnf",
    ".mylogin.cnf", ".claude/.credentials.json", ".claude.json",
)


class Refusal(Exception):
    """A bounded, non-sensitive error code safe to return to an agent."""


def sample_metadata(sample_id: str) -> dict:
    sample = SAMPLES[sample_id]
    return {"sample_id": sample_id, "mode": sample["mode"],
            "summary": sample["summary"],
            "additional_domains": list(sample["additional_domains"]),
            "limitations": list(sample["limitations"])}


def select_sample(args: argparse.Namespace) -> str:
    sample_id, mode = getattr(args, "sample", None), getattr(args, "mode", None)
    if (sample_id is None) == (mode is None):
        raise Refusal("SELECT_ONE_SAMPLE_OR_MODE")
    if mode is not None:
        if mode not in MODE_SAMPLES:
            raise Refusal("UNKNOWN_MODE")
        return MODE_SAMPLES[mode]
    if sample_id not in SAMPLES:
        raise Refusal("UNKNOWN_SAMPLE")
    return sample_id


def normalized_path(value: str) -> Path:
    path = Path(value)
    if (not path.is_absolute() or value.startswith("//") or str(path) != value or ".." in path.parts
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or any(char in value for char in '*?[]!\\(){}$`~')):
        raise Refusal("UNSAFE_PATH")
    return path


@contextlib.contextmanager
def directory(path: Path):
    """Walk from root without following symlinks, retaining the final directory."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def identity(fd: int) -> list[int]:
    info = os.fstat(fd)
    return [info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)]


def private_parent(fd: int) -> None:
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise Refusal("UNSAFE_OUTPUT_PARENT")


def read_output(parent: int, name: str) -> bytes | None:
    """Read only a bounded, private regular output, never a symlink or FIFO."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & 0o077):
            raise Refusal("UNSAFE_OUTPUT_FILE")
        if before.st_size > MAX_BYTES:
            raise Refusal("OUTPUT_TOO_LARGE")
        chunks = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        result = b"".join(chunks)
        after = os.fstat(fd)
        if len(result) > MAX_BYTES:
            raise Refusal("OUTPUT_TOO_LARGE")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise Refusal("OUTPUT_CHANGED_DURING_READ")
        return result
    finally:
        os.close(fd)


def within(path: Path, ancestor: Path) -> bool:
    return path == ancestor or ancestor in path.parents


def protected_paths(home: Path) -> list[Path]:
    return [home / suffix for suffix in CREDENTIAL_DIRS + CREDENTIAL_FILES]


def validate_layout(workspace: Path, home: Path, output: Path) -> None:
    if within(home, workspace):
        raise Refusal("WORKSPACE_CONTAINS_HOME")
    if any(within(workspace, item) for item in protected_paths(home)):
        raise Refusal("PROTECTED_WORKSPACE")
    if within(output, workspace):
        raise Refusal("OUTPUT_INSIDE_WORKSPACE")
    if any(within(output, item) for item in protected_paths(home)):
        raise Refusal("PROTECTED_OUTPUT")
    if (output.name in RESERVED_NAMES or output.suffix != ".json"
            or RESERVED_DIRECTORIES.intersection(output.parts[:-1])):
        raise Refusal("OUTPUT_MUST_BE_CANDIDATE_JSON")


def file_rules(tool: str, paths: list[Path], directories: list[Path]) -> list[str]:
    # Claude's absolute permission paths have a double leading slash.
    return ([f"{tool}(/{path})" for path in paths + directories]
            + [f"{tool}(/{path}/**)" for path in directories])


def build_settings(workspace: Path, user_home: Path, mode: str) -> dict:
    """Build one fixed candidate; empty arrays do not clear inherited arrays."""
    dirs = [user_home / suffix for suffix in CREDENTIAL_DIRS]
    files = [user_home / suffix for suffix in CREDENTIAL_FILES]
    denied = ["WebFetch", "WebSearch", "Agent", "Task"]
    denied += [f"Bash({command} *)" for command in (
        "sudo", "/bin/sudo", "/usr/bin/sudo", "su", "/bin/su", "/usr/bin/su")]
    denied += file_rules("Read", files, dirs)
    denied += file_rules("Edit", files, dirs)
    metadata = [workspace / ".git", workspace / ".claude"]
    denied += file_rules("Edit", [], metadata)
    for tool in ("Read", "Edit"):
        denied.extend([f"{tool}(/{workspace}/.env)", f"{tool}(/{workspace}/.env.*)"])
    if mode == "review":
        denied += ["Edit", "Write", "NotebookEdit", "Bash", "PowerShell", "Monitor"]
    credential_paths = [str(path) for path in files + dirs]
    return {
        "disableAutoMode": "disable",
        "useAutoModeDuringPlan": False,
        "permissions": {
            "defaultMode": "default",
            "disableBypassPermissionsMode": "disable",
            "deny": denied,
            "ask": ["Bash", "PowerShell", "Monitor", "Edit", "Write", "NotebookEdit"],
        },
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": False,
            "allowUnsandboxedCommands": False,
            "excludedCommands": [],
            "filesystem": {
                "disabled": False,
                "denyRead": credential_paths + [str(workspace / ".env")],
                "denyWrite": credential_paths + [str(path) for path in metadata]
                + [str(workspace / ".env")]
                + ([str(workspace)] if mode == "review" else []),
            },
            "network": {
                "allowedDomains": [],
                "strictAllowlist": True,
                "allowUnixSockets": [],
                "allowAllUnixSockets": False,
                "allowLocalBinding": False,
            },
        },
    }


def encode(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_plan(workspace: Path, home: Path, mode: str, output: Path, claude_version: str,
              descriptors: tuple[int, int, int], current: bytes | None,
              sample_id: str) -> dict:
    sample = sample_metadata(sample_id)
    settings = build_settings(workspace, home, mode)
    settings["sandbox"]["network"]["allowedDomains"] = sample["additional_domains"].copy()
    source = Path(__file__).read_bytes()
    binding = {
        "generator_version": VERSION,
        "generator_sha256": digest(source),
        "claude_version": claude_version,
        "workspace": str(workspace), "user_home": str(home),
        "mode": mode, "sample_id": sample_id, "output": str(output), "settings": settings,
        "directory_identities": [identity(fd) for fd in descriptors],
        "existing_output_sha256": None if current is None else digest(current),
    }
    return {
        "status": "CANDIDATE_PLAN", "runtime": "NOT_VERIFIED",
        "claude_version": claude_version,
        "plan_id": digest(encode(binding)),
        "workspace": str(workspace), "user_home": str(home),
        "output": str(output), "mode": mode, "sample_id": sample_id, "sample": sample,
        "output_exists": current is not None,
        "candidate_sha256": digest(encode(settings)), "settings": settings,
    }


def publish(parent: int, name: str, candidate: bytes) -> None:
    """Write fully then publish without replacing any existing directory entry."""
    temporary = ".acp-candidate-" + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        # link() fails if the destination exists, including a dangling symlink.
        os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent,
                follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=parent)
    os.fsync(parent)


def operate(args: argparse.Namespace) -> dict:
    if args.command == "samples":
        return {"status": "SAMPLE_CATALOGUE", "runtime": "NOT_VERIFIED",
                "samples": [sample_metadata(sample_id) for sample_id in SAMPLES]}
    if os.name != "posix":
        raise Refusal("UNSUPPORTED_HELPER_PLATFORM")
    sample_id = select_sample(args)
    mode = SAMPLES[sample_id]["mode"]
    workspace = normalized_path(args.workspace)
    home = normalized_path(args.user_home)
    output = normalized_path(args.output)
    validate_layout(workspace, home, output)
    if args.claude_version != "unknown" and not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.claude_version):
        raise Refusal("INVALID_CLAUDE_VERSION")
    with directory(workspace) as workspace_fd, directory(home) as home_fd, directory(output.parent) as parent:
        private_parent(parent)
        current = read_output(parent, output.name)
        plan = make_plan(workspace, home, mode, output, args.claude_version,
                         (workspace_fd, home_fd, parent), current, sample_id)
        if args.command == "plan":
            return plan
        candidate = encode(plan["settings"])
        if args.command == "verify":
            if current is None:
                raise Refusal("ARTIFACT_MISSING")
            if current != candidate:
                raise Refusal("ARTIFACT_MISMATCH")
            return {"status": "ARTIFACT_MATCH", "runtime": "NOT_VERIFIED",
                    "sample_id": sample_id,
                    "candidate_sha256": digest(candidate), "output": str(output)}
        if not re.fullmatch(r"[0-9a-f]{64}", args.plan_id or ""):
            raise Refusal("INVALID_PLAN_ID")
        if args.plan_id != plan["plan_id"]:
            raise Refusal("STALE_PLAN")
        if current is not None:
            raise Refusal("OUTPUT_EXISTS")
        publish(parent, output.name, candidate)
        return {"status": "CANDIDATE_EXPORTED", "runtime": "NOT_VERIFIED",
                "sample_id": sample_id,
                "candidate_sha256": digest(candidate), "output": str(output)}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal("INVALID_ARGUMENTS")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("samples", help="List the fixed scenario recommendations without filesystem access.")
    for command in ("plan", "export", "verify"):
        operation = commands.add_parser(command)
        operation.add_argument("--workspace", required=True)
        operation.add_argument("--user-home", required=True)
        selection = operation.add_mutually_exclusive_group(required=True)
        selection.add_argument("--sample", choices=tuple(SAMPLES))
        selection.add_argument("--mode", choices=tuple(MODE_SAMPLES),
                               help="Legacy alias for code-review or local-development.")
        operation.add_argument("--output", required=True)
        operation.add_argument("--claude-version", default="unknown")
        if command == "export":
            operation.add_argument("--plan-id", required=True)
    try:
        args = parser.parse_args(argv)
        result = operate(args)
    except Refusal as error:
        result = {"status": "BLOCKED", "reason": str(error), "runtime": "NOT_VERIFIED"}
    except OSError:
        # OS errors can embed paths, configuration data, or other sensitive text.
        result = {"status": "BLOCKED", "reason": "FILESYSTEM_ERROR", "runtime": "NOT_VERIFIED"}
    print(json.dumps(result, sort_keys=True))
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
