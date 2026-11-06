#!/usr/bin/env python3
"""Copy pinned skills without overwrites; detect partial installs from one manifest.

Offline, POSIX, Python 3.10+. No temporary directory, installer cache, rollback,
credential access, or execution of skill code. See docs/installation.md.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys


REPOSITORY = "DharmaDoll/agent-control-plane"
SKILLS = (
    "spec-driven-development", "controlled-github", "secret-checks",
    "codex-hardening", "claude-code-hardening",
)
MAX_FILES = 4096
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST_NAME = re.compile(r"skills-install(?:-[A-Za-z0-9][A-Za-z0-9._-]{0,63})?\.json\Z")
GIT_OVERRIDES = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG",
    "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_SHALLOW_FILE",
)


class Blocked(Exception):
    """A fixed, non-sensitive diagnostic code."""


class ExistingSkill(Exception):
    """Only the top-level exclusive mkdir found an existing skill."""


def io_reason(exc: OSError) -> str:
    return {
        errno.EACCES: "PERMISSION_DENIED", errno.EPERM: "PERMISSION_DENIED",
        errno.ENOSPC: "NO_SPACE_LEFT", errno.EROFS: "READ_ONLY_FILESYSTEM",
        errno.ELOOP: "SYMLINK_REJECTED", errno.ENOTDIR: "NOT_A_DIRECTORY",
        errno.ENOENT: "PATH_MISSING",
    }.get(exc.errno, "FILESYSTEM_ERROR")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_text(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 4096 and not any(
        ord(char) < 32 or ord(char) == 127 for char in value
    )


def absolute_path(value: str) -> Path:
    if (not clean_text(value) or not value.startswith("/") or value.startswith("//")
            or str(Path(value)) != value or ".." in Path(value).parts):
        raise Blocked("ABSOLUTE_NORMALIZED_PATH_REQUIRED")
    return Path(value)


def relative_path(value: str) -> tuple[str, ...]:
    if (not clean_text(value) or "\\" in value or value.startswith("/")
            or str(PurePosixPath(value)) != value):
        raise Blocked("INVALID_FILE_PATH")
    parts = PurePosixPath(value).parts
    if not parts or len(parts) > 32 or any(part in (".", "..") for part in parts):
        raise Blocked("INVALID_FILE_PATH")
    return parts


def location(destination: str, manifest: str) -> tuple[Path, Path]:
    dest, record = absolute_path(destination), absolute_path(manifest)
    if dest.name != "skills" or dest.parent.name not in (".agents", ".claude"):
        raise Blocked("STANDARD_SKILLS_DESTINATION_REQUIRED")
    if not MANIFEST_NAME.fullmatch(record.name):
        raise Blocked("SKILLS_INSTALL_JSON_NAME_REQUIRED")
    if any(parent.name == "skills" and parent.parent.name in (".agents", ".claude")
           for parent in record.parents):
        raise Blocked("MANIFEST_MUST_BE_OUTSIDE_SKILL_DIRECTORIES")
    return dest, record


def directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def descend(parent: int, parts: tuple[str, ...], create: bool = False) -> int:
    fd = os.dup(parent)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(part, directory_flags(), dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def directory(path: Path):
    root = os.open("/", directory_flags())
    try:
        fd = descend(root, path.parts[1:])
    finally:
        os.close(root)
    try:
        yield fd
    finally:
        os.close(fd)


def read_file(parent: int, name: str, limit: int) -> tuple[bytes, os.stat_result]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > limit):
            raise Blocked("UNSAFE_OR_OVERSIZED_FILE")
        chunks, length = [], 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            if length > limit:
                raise Blocked("UNSAFE_OR_OVERSIZED_FILE")
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_mode,
                before.st_nlink) != (after.st_size, after.st_mtime_ns,
                                    after.st_ctime_ns, after.st_mode, after.st_nlink):
            raise Blocked("FILE_CHANGED_DURING_READ")
        return b"".join(chunks), after
    finally:
        os.close(fd)


def write_file(parent: int, name: str, data: bytes, mode: int) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 mode, dir_fd=parent)
    try:
        remaining = memoryview(data)
        while remaining:
            count = os.write(fd, remaining)
            if not count:
                raise OSError(errno.EIO, "write failed")
            remaining = remaining[count:]
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(parent)


def git(source: Path, *args: str) -> bytes:
    # Object reads in a partial clone must not fetch from a promisor remote.
    # The empty protocol allowlist also protects Git versions without lazy-fetch
    # suppression. These are subprocess-only settings, never config writes.
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="",
               GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        completed = subprocess.run(
            ["git", "--no-pager", "--no-replace-objects", "-C", str(source), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("GIT_UNAVAILABLE_OR_TIMEOUT") from None
    if completed.returncode:
        raise Blocked("GIT_READ_FAILED")
    return completed.stdout


def blob(source: Path, object_id: str) -> bytes:
    try:
        size = int(git(source, "cat-file", "-s", object_id))
    except ValueError:
        raise Blocked("INVALID_GIT_SIZE") from None
    if not 0 <= size <= MAX_FILE_BYTES:
        raise Blocked("SOURCE_FILE_TOO_LARGE")
    data = git(source, "cat-file", "blob", object_id)
    if len(data) != size:
        raise Blocked("SOURCE_SIZE_CHANGED")
    return data


def source_manifest(source: Path, commit: str, dest: Path, names: list[str]) -> tuple[dict, dict]:
    if not SHA.fullmatch(commit):
        raise Blocked("FULL_COMMIT_SHA_REQUIRED")
    if any(name in os.environ for name in GIT_OVERRIDES):
        raise Blocked("GIT_ENV_OVERRIDE")
    with directory(source):
        pass
    if git(source, "rev-parse", "--show-toplevel").decode().rstrip("\n") != str(source):
        raise Blocked("SOURCE_ROOT_MISMATCH")
    urls = git(source, "config", "--get-all", "remote.origin.url").decode().splitlines()
    if urls not in ([f"https://github.com/{REPOSITORY}.git"], [f"https://github.com/{REPOSITORY}"]):
        raise Blocked("SOURCE_REPOSITORY_MISMATCH")
    if git(source, "rev-parse", "--verify", commit + "^{commit}").decode().strip() != commit:
        raise Blocked("COMMIT_MISMATCH")
    helper = blob(source, commit + ":scripts/manage_skills.py")
    helper_path = absolute_path(os.path.abspath(__file__))
    with directory(helper_path.parent) as fd:
        running, _ = read_file(fd, helper_path.name, MAX_FILE_BYTES)
    if helper != running:
        raise Blocked("HELPER_COMMIT_MISMATCH")
    result = {
        "format_version": 1, "repository": REPOSITORY, "commit": commit,
        "helper_sha256": digest(helper), "destination": str(dest), "skills": [],
    }
    payloads, total, count = {}, 0, 0
    for name in names:
        listing = git(source, "ls-tree", "-rz", "--full-tree", commit, "--", "skills/" + name)
        if len(listing) > MAX_MANIFEST_BYTES:
            raise Blocked("SOURCE_TREE_TOO_LARGE")
        files, contents = [], {}
        for line in listing.split(b"\0"):
            if not line:
                continue
            try:
                metadata, raw_path = line.split(b"\t", 1)
                mode, kind, oid = metadata.decode("ascii").split(" ")
                full_path = raw_path.decode("utf-8")
            except (ValueError, UnicodeError):
                raise Blocked("INVALID_SOURCE_TREE") from None
            prefix = "skills/" + name + "/"
            if (mode not in ("100644", "100755") or kind != "blob"
                    or not SHA.fullmatch(oid) or not full_path.startswith(prefix)):
                raise Blocked("UNSUPPORTED_SOURCE_ENTRY")
            path = full_path[len(prefix):]
            relative_path(path)
            count += 1
            if count > MAX_FILES:
                raise Blocked("TOO_MANY_FILES")
            data = blob(source, oid)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise Blocked("SOURCE_TOO_LARGE")
            if data.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                raise Blocked("LFS_PAYLOAD_UNSUPPORTED")
            contents[path] = data
            files.append({"path": path, "sha256": digest(data), "size": len(data),
                          "executable": mode == "100755"})
        if "SKILL.md" not in contents:
            raise Blocked("SOURCE_SKILL_MISSING")
        result["skills"].append({"name": name, "files": sorted(files, key=lambda f: f["path"])})
        payloads[name] = contents
    validate_manifest(result)
    return result, payloads


def keys(value: object, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise Blocked("INVALID_MANIFEST")


def validate_manifest(value: dict) -> dict:
    keys(value, {"format_version", "repository", "commit", "helper_sha256", "destination", "skills"})
    if (type(value["format_version"]) is not int or value["format_version"] != 1
            or value["repository"] != REPOSITORY
            or not isinstance(value["commit"], str) or not SHA.fullmatch(value["commit"])
            or not isinstance(value["helper_sha256"], str) or not DIGEST.fullmatch(value["helper_sha256"])):
        raise Blocked("INVALID_MANIFEST")
    dest = absolute_path(value["destination"])
    location(str(dest), str(dest.parent / "skills-install.json"))
    if not isinstance(value["skills"], list) or not 1 <= len(value["skills"]) <= len(SKILLS):
        raise Blocked("INVALID_MANIFEST")
    seen_names, count, total = set(), 0, 0
    for skill in value["skills"]:
        keys(skill, {"name", "files"})
        name = skill["name"]
        if not isinstance(name, str) or name not in SKILLS or name in seen_names:
            raise Blocked("INVALID_MANIFEST")
        seen_names.add(name)
        if not isinstance(skill["files"], list) or not skill["files"]:
            raise Blocked("INVALID_MANIFEST")
        seen, portable = set(), {}
        for entry in skill["files"]:
            keys(entry, {"path", "sha256", "size", "executable"})
            parts = relative_path(entry["path"])
            path = entry["path"]
            if (path in seen or not isinstance(entry["sha256"], str)
                    or not DIGEST.fullmatch(entry["sha256"])
                    or type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_FILE_BYTES
                    or type(entry["executable"]) is not bool):
                raise Blocked("INVALID_MANIFEST")
            seen.add(path)
            for depth in range(1, len(parts) + 1):
                prefix = "/".join(parts[:depth])
                folded = prefix.casefold()
                if folded in portable and portable[folded] != prefix:
                    raise Blocked("CASE_COLLISION")
                portable[folded] = prefix
            count += 1
            total += entry["size"]
        if ("SKILL.md" not in seen or any(
                "/".join(relative_path(path)[:depth]) in seen
                for path in seen for depth in range(1, len(relative_path(path))))):
            raise Blocked("INVALID_MANIFEST")
    if count > MAX_FILES or total > MAX_TOTAL_BYTES:
        raise Blocked("MANIFEST_TOO_LARGE")
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise Blocked("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    with directory(path.parent) as fd:
        data, _ = read_file(fd, path.name, MAX_MANIFEST_BYTES)
    try:
        value = validate_manifest(json.loads(data, object_pairs_hook=unique_object))
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise Blocked("INVALID_MANIFEST") from None
    location(value["destination"], str(path))
    return value


def save_manifest(parent: int, record: Path, value: dict) -> None:
    data = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
    if len(data) > MAX_MANIFEST_BYTES:
        raise Blocked("MANIFEST_TOO_LARGE")
    try:
        write_file(parent, record.name, data, 0o600)
    except FileExistsError:
        if load_manifest(record) != value:
            raise Blocked("EXISTING_MANIFEST_DIFFERS") from None


def copy_skill(dest_fd: int, name: str, files: list[dict], payloads: dict[str, bytes]) -> None:
    # The exclusive directory creation is the no-overwrite boundary. Never fill
    # an existing partial directory: verify it and let the operator decide.
    try:
        os.mkdir(name, 0o755, dir_fd=dest_fd)
    except FileExistsError:
        raise ExistingSkill from None
    os.fsync(dest_fd)
    skill_fd = os.open(name, directory_flags(), dir_fd=dest_fd)
    try:
        for entry in files:
            parts = relative_path(entry["path"])
            parent = descend(skill_fd, parts[:-1], create=True)
            try:
                write_file(parent, parts[-1], payloads[entry["path"]],
                           0o755 if entry["executable"] else 0o644)
            finally:
                os.close(parent)
    finally:
        os.close(skill_fd)


def inspect_skill(dest: Path, skill: dict) -> dict:
    expected = {item["path"]: item for item in skill["files"]}
    expected_dirs = set()
    for path in expected:
        parts = relative_path(path)
        expected_dirs.update("/".join(parts[:depth]) for depth in range(1, len(parts)))
    actual, actual_dirs, unreadable = {}, set(), []
    visited = 0
    actual_bytes = 0

    def walk(fd: int, prefix: str = "") -> None:
        nonlocal visited, actual_bytes
        for name in sorted(os.listdir(fd)):
            visited += 1
            if visited > MAX_FILES * 4:
                raise Blocked("INSTALLED_TREE_TOO_LARGE")
            path = prefix + name
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    actual_dirs.add(path)
                    child = os.open(name, directory_flags(), dir_fd=fd)
                    try:
                        if path.count("/") >= 32:
                            raise Blocked("INSTALLED_TREE_TOO_DEEP")
                        walk(child, path + "/")
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode) and path in expected:
                    if actual_bytes + info.st_size > MAX_TOTAL_BYTES:
                        raise Blocked("INSTALLED_TREE_TOO_LARGE")
                    data, info = read_file(fd, name, MAX_FILE_BYTES)
                    actual_bytes += len(data)
                    if actual_bytes > MAX_TOTAL_BYTES:
                        raise Blocked("INSTALLED_TREE_TOO_LARGE")
                    actual[path] = (digest(data), len(data), bool(info.st_mode & 0o111))
                elif stat.S_ISREG(info.st_mode):
                    actual[path] = None  # Do not read unexpected file contents.
                else:
                    unreadable.append(path)
            except (OSError, Blocked):
                unreadable.append(path)

    result = {"name": skill["name"], "status": "UNREADABLE"}
    try:
        with directory(dest / skill["name"]) as fd:
            walk(fd)
    except FileNotFoundError:
        result["status"] = "MISSING"
        return result
    except (OSError, Blocked):
        return result
    missing = sorted(set(expected) - set(actual))
    extra = sorted((set(actual) - set(expected)) | {p + "/" for p in actual_dirs - expected_dirs})
    changed = sorted(path for path, entry in expected.items() if path in actual and
                     actual[path] != (entry["sha256"], entry["size"], entry["executable"]))
    result.update({"status": "UNREADABLE" if unreadable else
                   "DIFFERENT" if missing or extra or changed else "MATCH",
                   "missing": missing, "extra": extra, "changed": changed,
                   "unreadable": sorted(set(unreadable))})
    return result


def verify(value: dict, record: Path, actions: dict | None = None) -> dict:
    items = [inspect_skill(Path(value["destination"]), skill) for skill in value["skills"]]
    if actions is not None:
        for item in items:
            item["action"] = actions.get(item["name"], "NOT_ATTEMPTED")
    passed = all(item["status"] == "MATCH" and item.get("action") not in
                 ("COPY_FAILED", "NOT_ATTEMPTED") for item in items)
    return {"status": "PASS" if passed else "INCOMPLETE", "manifest": str(record),
            "commit": value["commit"], "destination": value["destination"],
            "skills": items, "runtime": "NOT_VERIFIED"}


def install(source: Path, commit: str, dest: Path, record: Path, names: list[str]) -> dict:
    value, payloads = source_manifest(source, commit, dest, names)
    # Validate the existing path chain before creating the host directory.
    record_saved = False
    try:
        with directory(dest.parent.parent) as base:
            try:
                host = os.open(dest.parent.name, directory_flags(), dir_fd=base)
            except FileNotFoundError:
                os.mkdir(dest.parent.name, 0o755, dir_fd=base)
                os.fsync(base)
                host = os.open(dest.parent.name, directory_flags(), dir_fd=base)
            try:
                try:
                    current = os.open(dest.name, directory_flags(), dir_fd=host)
                except FileNotFoundError:
                    current = None
                if current is not None:
                    os.close(current)
                if record.parent == dest.parent:
                    save_manifest(host, record, value)
                else:
                    # The documented default keeps this record in the permitted
                    # acquisition directory, removed with the helper on success.
                    with directory(record.parent) as record_parent:
                        save_manifest(record_parent, record, value)
                record_saved = True
                # The expected manifest is fsynced before the first skill write.
                dest_fd = descend(host, (dest.name,), create=True)
            finally:
                os.close(host)
    except OSError as exc:
        if not record_saved:
            raise
        report = verify(value, record, {})
        report.update(status="INCOMPLETE", reason=io_reason(exc))
        return report
    actions, errors, interrupted = {}, [], False
    try:
        for skill in value["skills"]:
            name = skill["name"]
            try:
                try:
                    os.stat(name, dir_fd=dest_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    actions[name] = "SKIPPED_EXISTING"
                    continue
                copy_skill(dest_fd, name, skill["files"], payloads[name])
                actions[name] = "COPIED"
            except ExistingSkill:
                actions[name] = "SKIPPED_EXISTING"
            except (OSError, Blocked) as exc:
                actions[name] = "COPY_FAILED"
                errors.append({"name": name, "reason": io_reason(exc) if isinstance(exc, OSError) else str(exc)})
            except KeyboardInterrupt:
                actions[name] = "COPY_FAILED"
                interrupted = True
                break
    finally:
        os.close(dest_fd)
    report = verify(value, record, actions)
    if errors:
        report["errors"] = errors
    if interrupted:
        report.update(status="INCOMPLETE", reason="INTERRUPTED")
    return report


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Blocked("INVALID_ARGUMENTS")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True, parser_class=Parser)
    add = sub.add_parser("install", help="copy absent skill folders from a pinned local commit")
    add.add_argument("--source", required=True)
    add.add_argument("--commit", required=True)
    add.add_argument("--dest", required=True)
    add.add_argument("--manifest", required=True)
    selection = add.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="select the five named skills")
    selection.add_argument("--skill", action="append", choices=SKILLS)
    check = sub.add_parser("verify", help="read-only comparison against an expected manifest")
    check.add_argument("--manifest", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        if os.name != "posix" or not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY")):
            raise Blocked("UNSUPPORTED_PLATFORM")
        args = parse_args(sys.argv[1:] if argv is None else argv)
        record = absolute_path(args.manifest)
        if args.operation == "install":
            dest, record = location(args.dest, str(record))
            source = absolute_path(args.source)
            names = list(SKILLS) if args.all else [name for name in SKILLS if name in args.skill]
            if args.skill and len(names) != len(args.skill):
                raise Blocked("DUPLICATE_SKILL")
            report = install(source, args.commit, dest, record, names)
        else:
            report = verify(load_manifest(record), record)
        code = 0 if report["status"] == "PASS" else 1
    except Blocked as exc:
        report, code = {"status": "BLOCKED", "reason": str(exc)}, 2
    except OSError as exc:
        report, code = {"status": "BLOCKED", "reason": io_reason(exc)}, 2
    except UnicodeError:
        report, code = {"status": "BLOCKED", "reason": "ENCODING_ERROR"}, 2
    except KeyboardInterrupt:
        report, code = {"status": "BLOCKED", "reason": "INTERRUPTED_CHECK_MANIFEST"}, 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
