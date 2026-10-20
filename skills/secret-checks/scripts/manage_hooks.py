#!/usr/bin/env python3
"""Manage repository-local, versioned secret-check bundles; standard library only."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import stat
import subprocess
import sys
import tempfile

SKILL = Path(__file__).resolve().parents[1]
GIT = "/usr/bin/git"
HOOKS = ("pre-commit", "commit-msg", "pre-push")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
GITLEAKS_SHA256 = "88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509"
ALLOWED_FILES = {"scripts/scan_sensitive.py", "scripts/gitleaks_gate.py",
                 "gitleaks.toml", "bin/gitleaks", *("hooks/" + h for h in HOOKS)}
OVERRIDES = {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
             "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
             "GIT_NAMESPACE", "GIT_CONFIG_SYSTEM"}


class Blocked(Exception):
    """Only fixed, non-sensitive reason codes cross the CLI boundary."""


def run(argv, *, cwd=None, data=None, env=None, allowed=(0,)):
    try:
        r = subprocess.run(argv, cwd=cwd, input=data, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("PROCESS_UNAVAILABLE_OR_TIMEOUT") from None
    if r.returncode not in allowed:
        raise Blocked("GIT_OR_HOOK_OPERATION_FAILED")
    return r


def git(repo, *args, allowed=(0,)):
    return run([GIT, "-C", str(repo), *args], allowed=allowed)


def config_values(repo, *, local=False):
    args = ["config"] + (["--local"] if local else [])
    r = git(repo, *args, "--null", "--get-all", "core.hooksPath", allowed=(0, 1))
    return r.stdout.rstrip(b"\0").decode().split("\0") if r.returncode == 0 else []


def regular(path):
    return path.exists() and not path.is_symlink() and stat.S_ISREG(path.stat().st_mode)


def read_json(path):
    if not regular(path) or path.stat().st_size > 2 * 1024 * 1024:
        raise Blocked("INVALID_MANAGEMENT_RECORD")
    return json.loads(path.read_bytes())


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Repository:
    def __init__(self, path):
        if OVERRIDES.intersection(os.environ) or any(k.startswith("GIT_CONFIG_KEY_") for k in os.environ):
            raise Blocked("GIT_ENV_OVERRIDE")
        self.repo = Path(path).resolve(strict=True)
        root = Path(git(self.repo, "rev-parse", "--show-toplevel").stdout.decode().strip()).resolve()
        if root != self.repo:
            raise Blocked("REPOSITORY_ROOT_REQUIRED")
        self.gitdir = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.decode().strip()).resolve()
        common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.decode().strip()
        self.shared = Path(common).resolve() != self.gitdir or git(root, "worktree", "list", "--porcelain").stdout.count(b"worktree ") != 1
        self.directory = self.gitdir / "secret-checks"
        self.bundles = self.directory / "bundles"
        for path in (self.directory, self.bundles):
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                raise Blocked("UNSAFE_MANAGED_DIRECTORY")

    def load(self):
        path = self.directory / "state.json"
        if not path.exists() and not path.is_symlink():
            if self.directory.exists():
                raise Blocked("UNRECOGNIZED_MANAGED_DIRECTORY")
            return None
        state = read_json(path)
        if (state.get("schema") != 1 or state.get("repo") != str(self.repo)
                or state.get("gitdir") != str(self.gitdir) or not isinstance(state.get("bundles"), dict)):
            raise Blocked("INVALID_MANAGEMENT_RECORD")
        for key in ("active", "previous"):
            value = state.get(key)
            if value is not None and (not isinstance(value, str) or not DIGEST.fullmatch(value)
                                      or value not in state["bundles"]):
                raise Blocked("INVALID_MANAGEMENT_RECORD")
        for identity, record in state["bundles"].items():
            if not DIGEST.fullmatch(identity) or record.get("engine") not in ("python", "gitleaks"):
                raise Blocked("INVALID_MANAGEMENT_RECORD")
            files = record.get("files")
            if not isinstance(files, dict) or not files or not set(files) <= ALLOWED_FILES:
                raise Blocked("INVALID_MANAGEMENT_RECORD")
            for metadata in files.values():
                if (not isinstance(metadata, dict) or not DIGEST.fullmatch(metadata.get("sha256", ""))
                        or metadata.get("mode") not in (0o600, 0o700)):
                    raise Blocked("INVALID_MANAGEMENT_RECORD")
        return state

    def save(self, state):
        atomic_json(self.directory / "state.json", state)

    @contextmanager
    def lock(self, *, create=False):
        if self.shared:
            raise Blocked("REVIEW_WORKTREES")
        if create and not self.directory.exists():
            self.directory.mkdir(mode=0o700)
            self.bundles.mkdir(mode=0o700)
            self.save({"schema": 1, "repo": str(self.repo), "gitdir": str(self.gitdir),
                       "active": None, "previous": None, "bundles": {},
                       "original_local_hooks": [], "original_effective_hooks": []})
        if not self.directory.is_dir():
            raise Blocked("NOT_INSTALLED")
        fd = os.open(self.directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Blocked("UNSAFE_LOCK_FILE")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Blocked("MANAGEMENT_BUSY") from None
            yield
        finally:
            os.close(fd)

    def expected_config(self, state):
        if state["active"]:
            return [str(self.bundles / state["active"] / "hooks")]
        return []

    def assert_config(self, state):
        expected = self.expected_config(state)
        if config_values(self.repo) != expected or config_values(self.repo, local=True) != expected:
            raise Blocked("HOOK_CONFIGURATION_CHANGED")

    def bundle_clean(self, identity, record, *, partial=False):
        path = self.bundles / identity
        if path.is_symlink() or not path.is_dir():
            return False
        expected = set(record["files"])
        dirs = {str(parent) for name in expected for parent in Path(name).parents if str(parent) != "."}
        actual = set()
        for item in path.rglob("*"):
            name = item.relative_to(path).as_posix()
            if item.is_symlink():
                return False
            if item.is_dir():
                if name not in dirs:
                    return False
                continue
            if not regular(item) or name not in expected:
                return False
            if item.stat().st_size > 64 * 1024 * 1024:
                return False
            metadata = record["files"][name]
            if (hashlib.sha256(item.read_bytes()).hexdigest() != metadata["sha256"]
                    or stat.S_IMODE(item.stat().st_mode) != metadata["mode"]):
                return False
            actual.add(name)
        return actual <= expected if partial else actual == expected

    def inspect(self):
        state = self.load()
        configured = bool(config_values(self.repo))
        hooks_path = Path(git(self.repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks").stdout.decode().strip())
        count = 0
        if hooks_path.is_symlink():
            count = 1
        elif hooks_path.is_dir():
            count = sum(1 for p in hooks_path.iterdir() if not (p.name.endswith(".sample") and regular(p)))
        shallow = git(self.repo, "rev-parse", "--is-shallow-repository").stdout.strip() != b"false"
        keys = git(self.repo, "config", "--local", "--name-only", "--list").stdout.lower().splitlines()
        partial = b"extensions.partialclone" in keys or any(k.endswith(b".promisor") for k in keys)
        entries = [entry for entry in git(self.repo, "ls-files", "--stage", "-z").stdout.split(b"\0") if entry]
        unsupported = sum(1 for entry in entries if entry.split(b"\t", 1)[0].split()[0] not in (b"100644", b"100755")
                          or entry.split(b"\t", 1)[0].split()[2] != b"0")
        objects = {}
        for line in git(self.repo, "count-objects", "-v").stdout.splitlines():
            key, value = line.split(b": ", 1)
            if key in (b"count", b"in-pack", b"size", b"size-pack"):
                objects[key.decode()] = int(value)
        active = state["active"] if state else None
        recommendation = "INSTALL"
        if self.shared:
            recommendation = "REVIEW_WORKTREES"
        elif shallow or partial:
            recommendation = "REVIEW_CLONE"
        elif unsupported and not active:
            recommendation = "REVIEW_INDEX"
        elif active:
            try:
                self.assert_config(state)
                clean = self.bundle_clean(active, state["bundles"][active])
                recommendation = "VERIFY_OR_UPDATE" if clean else "REVIEW_MODIFIED_BUNDLE"
            except Blocked:
                recommendation = "REVIEW_CHANGED_CONFIGURATION"
        elif configured or count:
            recommendation = "REVIEW_EXISTING_HOOKS"
        scopes = git(self.repo, "config", "--show-scope", "--get-all", "core.hooksPath", allowed=(0, 1)).stdout
        scope_names = sorted({line.split(b"\t", 1)[0].decode() for line in scopes.splitlines()
                              if line.split(b"\t", 1)[0] in (b"local", b"global", b"system", b"worktree", b"command")})
        return {"status": "PASS", "recommendation": recommendation, "os": platform.system(),
                "python": platform.python_version(), "git": git(self.repo, "--version").stdout.decode().strip(),
                "configured_hooks": configured, "existing_hook_count": count,
                "shared_worktrees": self.shared, "shallow": shallow, "partial_clone": partial,
                "index_entries": len(entries), "unsupported_index_entries": unsupported,
                "object_database": objects,
                "hook_config_scopes": scope_names,
                "active": active, "engine": state["bundles"][active]["engine"] if active else None}


def source_payload(engine, binary):
    scanner = "scan_sensitive.py" if engine == "python" else "gitleaks_gate.py"
    payload = {"scripts/" + scanner: ((SKILL / "scripts" / scanner).read_bytes(), 0o600)}
    for hook in HOOKS:
        mode = {"pre-commit": "--staged", "commit-msg": '--file "$1" --label commit-message', "pre-push": "--pre-push"}[hook]
        if engine == "gitleaks":
            mode = hook
        template = (SKILL / "assets/hooks" / hook).read_text()
        # Python consumes only the message path; pre-push's remote args are not scanner options.
        if engine == "python":
            template = template.replace(' "$@"', "")
        text = template.replace("@PYTHON@", shlex.quote(str(Path(sys.executable).resolve())))
        text = text.replace("@SCANNER@", scanner).replace("@MODE@", mode)
        payload["hooks/" + hook] = (text.encode(), 0o700)
    if engine == "gitleaks":
        if platform.machine() != "x86_64" or not binary:
            raise Blocked("VERIFIED_LINUX_X64_GITLEAKS_REQUIRED")
        path = Path(binary)
        if not regular(path) or path.stat().st_size > 64 * 1024 * 1024:
            raise Blocked("INVALID_GITLEAKS_BINARY")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != GITLEAKS_SHA256:
            raise Blocked("GITLEAKS_DIGEST_MISMATCH")
        payload["bin/gitleaks"] = (data, 0o700)
        payload["gitleaks.toml"] = ((SKILL / "assets/gitleaks.toml").read_bytes(), 0o600)
    return payload


def isolated_probe(hooks):
    """Test the exact bundle with local Git; never commit in the target repository."""
    with tempfile.TemporaryDirectory(prefix="secret-checks-probe-") as raw:
        root = Path(raw)
        repo, remote = root / "work", root / "remote.git"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITLEAKS_", "PYTHON"))}
        env.update(HOME=raw, XDG_CONFIG_HOME=raw, GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL=os.devnull, LC_ALL="C.UTF-8")

        def call(*args, allowed=(0,), data=None, location=None):
            return run([GIT, *args], cwd=location or repo, data=data, env=env, allowed=allowed)

        call("init", "-q", "-b", "main", str(repo), location=root)
        call("init", "-q", "--bare", str(remote), location=root)
        call("config", "user.name", "Secret checks probe")
        call("config", "user.email", "probe@example.invalid")
        call("config", "core.hooksPath", str(hooks))
        file = repo / "example.txt"
        file.write_bytes(b"safe content\n")
        call("add", "example.txt")
        call("commit", "-q", "-m", "safe probe")
        baseline = call("rev-parse", "HEAD").stdout.strip()
        # Also exercise the explicit-SHA refspec used by controlled-github.
        call("push", "--quiet", str(remote), baseline.decode() + ":refs/heads/main")
        canary = ("-----BEGIN " + "PRIVATE KEY-----\n" + "!invalid!" * 10 + "\n-----END " + "PRIVATE KEY-----\n").encode()
        file.write_bytes(canary)
        call("add", "example.txt")
        file.write_bytes(b"safe working tree, different from index\n")
        rejected = call("commit", "-q", "-m", "blocked", allowed=tuple(range(256)))
        if rejected.returncode == 0 or b"REJECTED" not in rejected.stdout + rejected.stderr:
            raise Blocked("PROBE_SECRET_WAS_NOT_REJECTED")
        call("add", "example.txt")
        rejected = call("commit", "-q", "-F", "-", data=canary, allowed=tuple(range(256)))
        if rejected.returncode == 0 or b"REJECTED" not in rejected.stdout + rejected.stderr:
            raise Blocked("PROBE_MESSAGE_WAS_NOT_REJECTED")
        file.write_bytes(b"safe\0unscannable")
        call("add", "example.txt")
        rejected = call("commit", "-q", "-m", "incomplete", allowed=tuple(range(256)))
        diagnostic = rejected.stdout + rejected.stderr
        if rejected.returncode == 0 or not any(marker in diagnostic for marker in (b"ERROR", b"INCOMPLETE")):
            raise Blocked("PROBE_INCOMPLETE_WAS_NOT_REJECTED")
        # Build synthetic history without invoking commit hooks, then exercise pre-push.
        file.write_bytes(canary)
        call("add", "example.txt")
        tree = call("write-tree").stdout.strip().decode()
        bad = call("commit-tree", tree, "-p", baseline.decode(), "-m", "inert history probe").stdout.strip().decode()
        file.write_bytes(b"safe final tree\n")
        call("add", "example.txt")
        tree = call("write-tree").stdout.strip().decode()
        final = call("commit-tree", tree, "-p", bad, "-m", "removed inert probe").stdout.strip().decode()
        call("update-ref", "refs/heads/main", final)
        rejected = call("push", "--quiet", str(remote), "refs/heads/main:refs/heads/main", allowed=tuple(range(256)))
        if rejected.returncode == 0 or b"REJECTED" not in rejected.stdout + rejected.stderr:
            raise Blocked("PROBE_HISTORY_WAS_NOT_REJECTED")
        if call("rev-parse", "refs/heads/main", location=remote).stdout.strip() != baseline:
            raise Blocked("PROBE_REMOTE_CHANGED")
        for output in (rejected.stdout, rejected.stderr):
            if canary in output:
                raise Blocked("PROBE_VALUE_WAS_DISCLOSED")


def activate(repo, action, engine, binary):
    inspection = repo.inspect()
    state = repo.load()
    if state and state["active"]:
        repo.assert_config(state)
        if not repo.bundle_clean(state["active"], state["bundles"][state["active"]]):
            raise Blocked("ACTIVE_BUNDLE_MODIFIED")
    elif inspection["recommendation"] != "INSTALL":
        reason = "EXISTING_HOOKS" if inspection["recommendation"] == "REVIEW_EXISTING_HOOKS" else inspection["recommendation"]
        raise Blocked(reason)
    elif action == "update":
        raise Blocked("NOT_INSTALLED")
    chosen = engine or (state["bundles"][state["active"]]["engine"] if state and state["active"] else "python")
    if binary is not None and chosen != "gitleaks":
        raise Blocked("GITLEAKS_BINARY_REQUIRES_GITLEAKS_ENGINE")
    if state and state["active"] and engine is None and chosen == "gitleaks" and binary is None:
        binary = repo.bundles / state["active"] / "bin/gitleaks"
    payload = source_payload(chosen, binary)
    files = {name: {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode} for name, (data, mode) in payload.items()}
    identity = hashlib.sha256(json.dumps({"engine": chosen, "files": files}, sort_keys=True).encode()).hexdigest()
    with repo.lock(create=True):
        state = repo.load()
        repo.assert_config(state)
        if state["active"] == identity:
            if not repo.bundle_clean(identity, state["bundles"][identity]):
                raise Blocked("ACTIVE_BUNDLE_MODIFIED")
            return {"status": "PASS", "action": "UNCHANGED", "active": identity, "engine": chosen}
        if action == "install" and state["active"]:
            raise Blocked("USE_UPDATE_FOR_DIFFERENT_VERSION")
        path = repo.bundles / identity
        if identity in state["bundles"]:
            if not repo.bundle_clean(identity, state["bundles"][identity]):
                raise Blocked("EXISTING_BUNDLE_MODIFIED_OR_INCOMPLETE")
        else:
            if path.exists() or path.is_symlink():
                raise Blocked("UNKNOWN_BUNDLE_EXISTS")
            # Record the exact expected files before writing, for interrupted-install cleanup.
            state["bundles"][identity] = {"engine": chosen, "files": files, "status": "prepared"}
            repo.save(state)
            path.mkdir(mode=0o700)
            for name, (data, mode) in payload.items():
                target = path / name
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(data)
                target.chmod(mode)
        isolated_probe(path / "hooks")
        if not repo.bundle_clean(identity, state["bundles"][identity]):
            raise Blocked("PREPARED_BUNDLE_CHANGED")
        repo.assert_config(state)
        if repo.shared:
            raise Blocked("REVIEW_WORKTREES")
        old_active = state["active"]
        old_previous = state["previous"]
        expected = [str(path / "hooks")]
        try:
            git(repo.repo, "config", "--local", "core.hooksPath", expected[0])
            if config_values(repo.repo) != expected or config_values(repo.repo, local=True) != expected:
                raise Blocked("CONFIGURATION_READBACK_FAILED")
            state["previous"] = old_active
            state["active"] = identity
            state["bundles"][identity]["status"] = "ready"
            repo.save(state)
        except (OSError, Blocked):
            # Restore only a value we can still identify as our own write.
            if config_values(repo.repo, local=True) == expected:
                if old_active:
                    git(repo.repo, "config", "--local", "core.hooksPath", str(repo.bundles / old_active / "hooks"))
                else:
                    git(repo.repo, "config", "--local", "--unset-all", "core.hooksPath")
            state["active"], state["previous"] = old_active, old_previous
            raise
        return {"status": "PASS", "action": action.upper(), "active": identity,
                "engine": chosen, "configuration": "PASS", "isolated_hooks": "PASS"}


def managed_operation(repo, action, apply):
    if repo.load() is None:
        if action == "cleanup":
            return {"status": "PASS", "candidates": [], "removed": [], "kept": []}
        raise Blocked("NOT_INSTALLED")
    with repo.lock():
        state = repo.load()
        repo.assert_config(state)
        if action == "verify":
            active = state["active"]
            if not active:
                raise Blocked("NOT_INSTALLED")
            if not repo.bundle_clean(active, state["bundles"][active]):
                raise Blocked("ACTIVE_BUNDLE_MODIFIED")
            isolated_probe(repo.bundles / active / "hooks")
            repo.assert_config(state)
            return {"status": "PASS", "configuration": "PASS", "integrity": "PASS", "isolated_hooks": "PASS"}
        if action == "uninstall":
            if state["active"]:
                active, previous = state["active"], state["previous"]
                try:
                    git(repo.repo, "config", "--local", "--unset-all", "core.hooksPath")
                    if config_values(repo.repo):
                        raise Blocked("RESTORE_READBACK_FAILED")
                    state["active"] = None
                    state["previous"] = None
                    repo.save(state)
                except (OSError, Blocked):
                    if not config_values(repo.repo) and not config_values(repo.repo, local=True):
                        git(repo.repo, "config", "--local", "core.hooksPath", str(repo.bundles / active / "hooks"))
                    state["active"], state["previous"] = active, previous
                    raise
            return {"status": "PASS", "action": "UNINSTALL", "bundles_retained": len(state["bundles"])}
        if action == "rollback":
            previous, active = state["previous"], state["active"]
            if not active or not previous:
                raise Blocked("NO_ROLLBACK_VERSION")
            if not repo.bundle_clean(previous, state["bundles"][previous]):
                raise Blocked("ROLLBACK_BUNDLE_MODIFIED")
            isolated_probe(repo.bundles / previous / "hooks")
            repo.assert_config(state)
            git(repo.repo, "config", "--local", "core.hooksPath", str(repo.bundles / previous / "hooks"))
            state["active"], state["previous"] = previous, active
            try:
                repo.assert_config(state)
                repo.save(state)
            except (OSError, Blocked):
                if config_values(repo.repo, local=True) == [str(repo.bundles / previous / "hooks")]:
                    git(repo.repo, "config", "--local", "core.hooksPath", str(repo.bundles / active / "hooks"))
                raise
            return {"status": "PASS", "action": "ROLLBACK", "active": previous,
                    "configuration": "PASS", "isolated_hooks": "PASS"}
        protected = {state["active"], state["previous"]} if state["active"] else set()
        candidates, kept, removed = [], [], []
        for identity, record in list(state["bundles"].items()):
            if identity in protected:
                kept.append({"bundle": identity, "reason": "ACTIVE_OR_ROLLBACK"})
            elif repo.bundle_clean(identity, record, partial=True):
                candidates.append(identity)
            elif not (repo.bundles / identity).exists() and not (repo.bundles / identity).is_symlink():
                if apply:
                    del state["bundles"][identity]
            else:
                kept.append({"bundle": identity, "reason": "UNKNOWN_OR_MODIFIED_CONTENT"})
        known = set(state["bundles"])
        for path in repo.bundles.iterdir():
            if path.name not in known:
                kept.append({"reason": "UNTRACKED_ENTRY"})
        for path in repo.directory.iterdir():
            if path.name not in {"state.json", "lock", "bundles"}:
                kept.append({"reason": "UNTRACKED_MANAGEMENT_ENTRY"})
        if apply:
            for identity in candidates:
                repo.assert_config(state)
                record = state["bundles"][identity]
                if not repo.bundle_clean(identity, record, partial=True):
                    raise Blocked("CLEANUP_CANDIDATE_CHANGED")
                directory = repo.bundles / identity
                # Delete only reviewed files; never recursively remove an unchecked directory.
                for name in record["files"]:
                    path = directory / name
                    if path.exists():
                        path.unlink()
                for path in sorted(directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                    path.rmdir()
                directory.rmdir()
                del state["bundles"][identity]
                removed.append(identity)
            repo.save(state)
        return {"status": "PASS", "action": "CLEANUP" if apply else "PREVIEW",
                "candidates": candidates, "removed": removed, "kept": kept}


def main():
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise Blocked("INVALID_ARGUMENTS")
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("action", choices=("inspect", "install", "verify", "update", "rollback", "uninstall", "cleanup"))
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--engine", choices=("python", "gitleaks"))
        parser.add_argument("--gitleaks", type=Path)
        parser.add_argument("--apply", action="store_true", help="Delete cleanup candidates; otherwise preview only")
        args = parser.parse_args()
        if platform.system() != "Linux" or sys.version_info < (3, 10):
            raise Blocked("UNSUPPORTED_PLATFORM")
        if (args.apply and args.action != "cleanup") or (args.action not in ("install", "update") and (args.engine or args.gitleaks)):
            raise Blocked("INVALID_ARGUMENTS")
        repo = Repository(args.repo)
        if args.action == "inspect":
            result = repo.inspect()
        elif args.action in ("install", "update"):
            result = activate(repo, args.action, args.engine, args.gitleaks)
        else:
            result = managed_operation(repo, args.action, args.apply)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Blocked as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print(json.dumps({"status": "BLOCKED", "reason": "INVALID_INPUT_OR_MANAGEMENT_STATE"}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
