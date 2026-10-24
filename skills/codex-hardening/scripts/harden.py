"""Manage narrowly scoped Codex hardening profiles (Python 3.11+, Linux).

No shell, network downloads, model calls, credential reads or base-config writes.
The local account, trusted native Codex binary and this skill are trust anchors.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "compatibility" / "recipes.json"
MAX_FILE = 1024 * 1024
MAX_OUTPUT = 128 * 1024
MODES = ("review", "development")
STATE_DIR = "codex-hardening-state"
# Non-security preferences and known inspected settings. Unknown keys stop apply;
# they are never silently stripped from the user's configuration.
KNOWN_KEYS = {
    "model", "model_reasoning_effort", "model_reasoning_summary", "model_verbosity",
    "personality", "service_tier", "hide_agent_reasoning", "projects",
    "sandbox_mode", "sandbox_workspace_write", "approval_policy",
    "approvals_reviewer", "allow_login_shell", "web_search", "history",
    "shell_environment_policy", "cli_auth_credentials_store",
    "mcp_oauth_credentials_store", "mcp_servers", "otel", "log_dir",
    "memories", "features", "permissions", "default_permissions",
}


class Stop(Exception):
    """Only fixed reason codes may reach public diagnostics."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def checked_path(path, directory=False):
    path = Path(os.path.abspath(path))
    # Reject links in every component, not only the final file. Deliberately do
    # not silently resolve a user's management destination to a different tree.
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise Stop("SYMLINK_PATH")
    if directory and not path.is_dir():
        raise Stop("DIRECTORY_REQUIRED")
    return path


def read_file(path, limit=MAX_FILE):
    path = checked_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise Stop("UNSUPPORTED_FILE")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise Stop("INPUT_LIMIT")
        return data


def parse_toml(data):
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise Stop("INVALID_TOML") from None


def load_json(path):
    data = read_file(path)
    if data is None:
        return None
    try:
        return json.loads(data)
    except (ValueError, RecursionError):
        raise Stop("INVALID_JSON") from None


def render_profile(mode):
    if mode not in MODES:
        raise Stop("UNKNOWN_MODE")
    access = "read" if mode == "review" else "write"
    name = "acp-" + mode
    return (
        '# Managed by codex-hardening. Select explicitly; not a global policy.\n'
        f'default_permissions = "{name}"\n'
        'approval_policy = "on-request"\n'
        'approvals_reviewer = "user"\n'
        'allow_login_shell = false\n'
        f'\n[permissions.{name}]\n'
        'extends = ":read-only"\n'
        f'\n[permissions.{name}.filesystem.":workspace_roots"]\n'
        f'"." = "{access}"\n'
        '".git" = "read"\n'
        '".agents" = "read"\n'
        '".codex" = "read"\n'
        '".aws" = "read"\n'
        f'\n[permissions.{name}.network]\n'
        'enabled = false\n'
    )


def clean_env(home):
    # Do not pass API keys, proxies, PYTHON*, LD_*, shell startup or real HOME.
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "CODEX_HOME": str(home),
            "LANG": "C.UTF-8"}


def run(argv, home, cwd, timeout=15):
    """Bound subprocess output/time and discard raw diagnostics at the boundary."""
    process = subprocess.Popen(argv, cwd=cwd, env=clean_env(home), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    output = [bytearray(), bytearray()]
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for number, stream in enumerate((process.stdout, process.stderr)):
                selector.register(stream, selectors.EVENT_READ, number)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Stop("PROCESS_TIMEOUT")
                for key, _ in selector.select(min(remaining, 0.1)):
                    block = os.read(key.fileobj.fileno(), 8192)
                    if not block:
                        selector.unregister(key.fileobj)
                    else:
                        output[key.data].extend(block)
                        if sum(map(len, output)) > MAX_OUTPUT:
                            raise Stop("PROCESS_OUTPUT_LIMIT")
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return code, bytes(output[0]), bytes(output[1])
    finally:
        # Also terminate descendants retaining no pipes after their parent exits.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()


def executable_identity(binary):
    binary = checked_path(binary)
    info = binary.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(binary, os.X_OK):
        raise Stop("EXECUTABLE_REQUIRED")
    if info.st_mode & 0o022 or info.st_size > 512 * MAX_FILE:
        raise Stop("UNSAFE_EXECUTABLE")
    hasher = hashlib.sha256()
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise Stop("NATIVE_ELF_REQUIRED")
        stream.seek(0)
        for block in iter(lambda: stream.read(MAX_FILE), b""):
            hasher.update(block)
    return {"path": str(binary), "sha256": hasher.hexdigest()}


def detect(binary):
    identity = executable_identity(binary)
    with tempfile.TemporaryDirectory(prefix="codex-hardening-identify-") as temporary:
        rc, output, _ = run([str(binary), "--version"], temporary, temporary)
        match = re.fullmatch(rb"codex-cli (\d+\.\d+\.\d+)\s*", output)
        version = match[1].decode() if rc == 0 and match else "unknown"
        config = load_json(RECIPES)
        if not isinstance(config, dict) or config.get("schema") != 1:
            raise Stop("RECIPE_SCHEMA_UNSUPPORTED")
        recipe = next((item for item in config["recipes"] if version in item["versions"]
                       and item["platform"] == sys.platform
                       and platform.machine() in item["machine"]), None)
        if recipe:
            if recipe["renderer"] != "permissions-v1" or recipe["probe"] != "sandbox-permissions-v1":
                raise Stop("RECIPE_HANDLER_UNSUPPORTED")
            commands = {"root": ["--help"], "sandbox": ["sandbox", "--help"],
                        "rules": ["execpolicy", "check", "--help"]}
            for key, markers in recipe["required_help"].items():
                rc, output, _ = run([str(binary), *commands[key]], temporary, temporary)
                if rc or any(marker.encode() not in output for marker in markers):
                    raise Stop("CLI_CAPABILITY_MISMATCH")
    return identity, version, recipe


class Manager:
    def __init__(self, home, workspace, binary, mode):
        self.home = checked_path(home, directory=True)
        self.workspace = checked_path(workspace, directory=True)
        self.binary = checked_path(binary)
        if mode not in MODES:
            raise Stop("UNKNOWN_MODE")
        self.mode = mode
        self.name = "acp-" + mode
        self.target = self.home / (self.name + ".config.toml")
        self.directory = self.home / STATE_DIR
        self.state_path = self.directory / (mode + ".json")
        self.journal = self.directory / (mode + ".pending.json")

    def layers(self):
        # Conservative superset: inspect every ancestor instead of guessing the
        # repo/trust boundary. System/managed layers need a separate adapter.
        paths = [(self.home / "config.toml", "user")]
        for name in ("config.toml", "requirements.toml", "managed_config.toml"):
            paths.append((Path("/etc/codex") / name, "managed"))
        for name in ("requirements.toml", "managed_config.toml"):
            paths.append((self.home / name, "managed"))
        for parent in reversed((self.workspace, *self.workspace.parents)):
            paths.append((parent / ".codex" / "config.toml", "project"))
            paths.append((parent / ".codex" / "hooks.json", "hooks"))
        paths.append((self.home / "hooks.json", "hooks"))
        for base in [self.home, *(p / ".codex" for p in (self.workspace, *self.workspace.parents))]:
            rules = checked_path(base / "rules")
            if rules.exists():
                if not rules.is_dir():
                    raise Stop("UNSUPPORTED_RULE_DIRECTORY")
                entries = list(rules.iterdir())
                if len(entries) > 200:
                    raise Stop("INPUT_LIMIT")
                for item in sorted(entries):
                    paths.append((item, "rules"))
        # Deduplicate overlapping home/workspace layers.
        return list(dict.fromkeys(paths))

    def inspect(self):
        identity, version, recipe = detect(self.binary)
        issues, fingerprints, observations = [], {}, {}
        if not recipe:
            issues.append("UNSUPPORTED_VERSION_OR_PLATFORM")
        layers = self.layers()
        if len(layers) > 400:
            raise Stop("INPUT_LIMIT")
        total = 0
        for path, kind in layers:
            data = read_file(path)
            total += len(data) if data else 0
            if total > 8 * MAX_FILE:
                raise Stop("INPUT_LIMIT")
            fingerprints[str(path)] = None if data is None else digest(data)
            if data is None:
                continue
            if kind in ("managed", "project", "hooks", "rules"):
                # Do not evaluate arbitrary rule text or start project hooks.
                issues.append("REVIEW_REQUIRED_" + kind.upper())
                continue
            config = parse_toml(data)
            if set(config) - KNOWN_KEYS:
                issues.append("UNREVIEWED_CONFIG_KEYS")
            if any(key in config for key in ("sandbox_mode", "sandbox_workspace_write",
                                              "permissions", "default_permissions")):
                issues.append("PERMISSION_MODEL_CONFLICT")
            if config.get("features"):
                issues.append("FEATURE_FLAGS_REQUIRE_REVIEW")
            if config.get("otel"):
                issues.append("TELEMETRY_REQUIRES_REVIEW")
            projects = config.get("projects", {})
            if not isinstance(projects, dict) or any(
                not isinstance(value, dict) or set(value) != {"trust_level"}
                or value["trust_level"] not in ("trusted", "untrusted")
                for value in projects.values()
            ):
                issues.append("PROJECT_SETTINGS_REQUIRE_REVIEW")
            # All counts / enums, never user-supplied names, URLs or values.
            for key in ("mcp_servers", "otel", "memories", "shell_environment_policy", "log_dir"):
                observations[key] = "configured" if key in config else "not_explicit"
            history = config.get("history", {})
            persistence = history.get("persistence") if isinstance(history, dict) else None
            observations["history_persistence"] = (persistence if persistence in ("none", "save-all")
                                                   else "not_explicit_or_unknown")
            for key, allowed in {
                "web_search": ("cached", "indexed", "live", "disabled"),
                "sandbox_mode": ("read-only", "workspace-write", "danger-full-access"),
                "approval_policy": ("on-request", "never", "untrusted", "on-failure"),
                "approvals_reviewer": ("user", "auto_review"),
                "cli_auth_credentials_store": ("file", "keyring", "auto"),
                "mcp_oauth_credentials_store": ("file", "keyring", "auto"),
            }.items():
                value = config.get(key)
                observations[key] = value if value in allowed else "not_explicit_or_unknown"
            observations["allow_login_shell"] = (config["allow_login_shell"]
                if type(config.get("allow_login_shell")) is bool else "not_explicit_or_unknown")
            shell = config.get("shell_environment_policy", {})
            inheritance = shell.get("inherit") if isinstance(shell, dict) else None
            observations["shell_environment_inherit"] = (inheritance
                if inheritance in ("all", "core", "none") else "not_explicit_or_unknown")
        target = read_file(self.target)
        fingerprints[str(self.target)] = None if target is None else digest(target)
        state = self.state()
        if target is not None and state is None:
            issues.append("UNMANAGED_PROFILE_COLLISION")
        if state and target != self.content(state["current"]):
            issues.append("MANAGED_PROFILE_DRIFT")
        if read_file(self.journal) is not None:
            issues.append("INTERRUPTED_TRANSACTION")
        internal = {"executable": identity, "version": version, "mode": self.mode,
                    "workspace": str(self.workspace), "home": str(self.home),
                    "files": fingerprints, "state": state,
                    "recipe_digest": digest(read_file(RECIPES)),
                    "script_digest": digest(read_file(Path(__file__))),
                    "python": {"path": sys.executable, "version": sys.version},
                    "platform": platform.platform(), "uid": os.getuid()}
        return {"status": "READY" if not issues else "BLOCKED",
                "version": version, "recipe": recipe["id"] if recipe else None,
                "issues": sorted(set(issues)), "observations": observations,
                "fingerprint": digest(encoded(internal)), "profile": self.name,
                "runtime": "NOT_VERIFIED", "other_surfaces": "NOT_VERIFIED"}

    @staticmethod
    def content(text):
        return None if text is None else text.encode()

    def state(self):
        state = load_json(self.state_path)
        if state is not None:
            if (not isinstance(state, dict) or set(state) != {"schema", "current", "previous"}
                    or state["schema"] != 1):
                raise Stop("STATE_SCHEMA_UNSUPPORTED")
            for value in (state["current"], state["previous"]):
                if value is not None and (not isinstance(value, str) or len(value) > 8192):
                    raise Stop("INVALID_STATE")
        return state

    def plan(self):
        report = self.inspect()
        report["candidate"] = render_profile(self.mode)
        report["plan_id"] = digest(encoded(report))
        report["operation"] = "plan"
        return report

    @contextmanager
    def locked(self):
        home_info = self.home.stat()
        if home_info.st_uid != os.getuid() or home_info.st_mode & 0o022:
            raise Stop("UNSAFE_MANAGEMENT_HOME")
        checked_path(self.directory)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Stop("UNSAFE_STATE_DIRECTORY")
        lock = checked_path(self.directory / "lock")
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                raise Stop("UNSAFE_LOCK")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop("BUSY") from None
            yield
        finally:
            os.close(fd)

    @staticmethod
    def atomic(path, data):
        checked_path(path)
        fd, temporary = tempfile.mkstemp(prefix=".acp-write-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def replace_target(self, text):
        if text is None:
            checked_path(self.target)
            self.target.unlink(missing_ok=True)
        else:
            self.atomic(self.target, text.encode())

    def transition(self, state, current):
        before = state["current"] if state else None
        if read_file(self.target) != self.content(before):
            raise Stop("MANAGED_PROFILE_DRIFT")
        if read_file(self.journal) is not None:
            raise Stop("INTERRUPTED_TRANSACTION")
        after = {"schema": 1, "current": current, "previous": before}
        self.atomic(self.journal, encoded({"schema": 1, "before": state, "after": after}))
        self.replace_target(current)
        self.atomic(self.state_path, encoded(after))
        self.journal.unlink()
        return {"status": "APPLIED", "profile": self.name, "runtime": "NOT_VERIFIED"}

    def apply(self, plan_id):
        with self.locked():
            plan = self.plan()
            if plan["status"] != "READY":
                raise Stop("PLAN_BLOCKED")
            if plan["plan_id"] != plan_id:
                raise Stop("STALE_PLAN")
            state = self.state()
            if state and state["current"] == render_profile(self.mode):
                return {"status": "UNCHANGED", "runtime": "NOT_VERIFIED"}
            # Candidate verification uses no original config or secrets.
            result = probe(self.binary, self.mode)
            if result["status"] != "PASS":
                return result
            if self.plan()["plan_id"] != plan_id:
                raise Stop("STALE_PLAN")
            return self.transition(state, render_profile(self.mode))

    def verify(self):
        before = self.inspect()
        if before["status"] != "READY" or read_file(self.target) != render_profile(self.mode).encode():
            raise Stop("VERIFY_PRECONDITION_FAILED")
        result = probe(self.binary, self.mode, self.home, self.workspace)
        after = self.inspect()
        if before["fingerprint"] != after["fingerprint"]:
            raise Stop("ENVIRONMENT_CHANGED_DURING_VERIFY")
        result["fingerprint"] = after["fingerprint"]
        # No persisted PASS cache: verify always re-runs. This prevents a stale
        # local receipt from becoming an authorization or startup bypass.
        result["other_surfaces"] = "NOT_VERIFIED"
        return result

    def rollback(self):
        with self.locked():
            pending = load_json(self.journal)
            if pending is not None:
                if (not isinstance(pending, dict) or set(pending) != {"schema", "before", "after"}
                        or pending["schema"] != 1):
                    raise Stop("INVALID_JOURNAL")
                before, after = pending["before"], pending["after"]
                # All recovery data are generated profile texts; reject malformed
                # state before touching the destination.
                for record in (before, after):
                    if record is not None and (not isinstance(record, dict)
                            or set(record) != {"schema", "current", "previous"}
                            or record["schema"] != 1
                            or any(v is not None and (not isinstance(v, str) or len(v) > 8192)
                                   for v in (record["current"], record["previous"]))):
                        raise Stop("INVALID_JOURNAL")
                old = before["current"] if before else None
                if after is None or read_file(self.target) not in (
                        self.content(old), self.content(after["current"])):
                    raise Stop("RECOVERY_DRIFT")
                if self.state() not in (before, after):
                    raise Stop("RECOVERY_STATE_DRIFT")
                self.replace_target(old)
                if before is None:
                    self.state_path.unlink(missing_ok=True)
                else:
                    self.atomic(self.state_path, encoded(before))
                self.journal.unlink()
                return {"status": "RECOVERED", "runtime": "NOT_VERIFIED"}
            state = self.state()
            if not state:
                raise Stop("NO_MANAGED_STATE")
            result = self.transition(state, state["previous"])
            result["status"] = "RESTORED"
            return result

    def uninstall(self):
        with self.locked():
            state = self.state()
            if state is None and read_file(self.target) is None:
                return {"status": "UNCHANGED"}
            if state is None:
                raise Stop("UNMANAGED_PROFILE_COLLISION")
            if state["current"] is None and read_file(self.target) is None:
                return {"status": "UNCHANGED"}
            result = self.transition(state, None)
            result["status"] = "UNINSTALLED"
            return result

    def cleanup(self, apply=False):
        # Only this mode's inactive record is eligible; the permanent lock inode,
        # active state, pending journal, other mode and unknown files are retained.
        def candidates():
            state = self.state()
            return bool(state and state["current"] is None and read_file(self.target) is None
                        and read_file(self.journal) is None)
        if not apply:
            return {"status": "PREVIEW", "eligible_records": int(candidates()),
                    "rollback_will_be_lost": candidates()}
        with self.locked():
            eligible = candidates()
            if eligible:
                self.state_path.unlink()
            return {"status": "CLEANED", "removed_records": int(eligible),
                    "retained": "lock, active/pending/unknown files and other profiles"}


# Probe stdout is a tiny fixed protocol. A process exit or timeout without the
# protocol is incomplete, not a policy denial. No payloads or errors are echoed.
PROBE_CODE = '''import errno, os, socket, sys
print("START", flush=True)
operation, target = sys.argv[1:3]
try:
    if operation == "write":
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    elif operation == "network":
        with socket.create_connection(("127.0.0.1", int(target)), timeout=2):
            pass
    else:
        raise RuntimeError()
except OSError as error:
    if error.errno in (errno.EACCES, errno.EPERM, errno.EROFS, errno.ENETUNREACH):
        print("DENIED")
    else:
        print("INCOMPLETE")
else:
    print("ALLOWED")
'''


def probe(binary, mode, home=None, workspace=None):
    """Run only local synthetic checks. Caller authorizes temporary probe writes."""
    with tempfile.TemporaryDirectory(prefix="codex-hardening-probe-") as temporary:
        root = Path(temporary)
        candidate_home = root / "home"
        candidate_home.mkdir()
        candidate_workspace = root / "workspace"
        candidate_workspace.mkdir()
        selected_home = Path(home) if home else candidate_home
        selected_workspace = Path(workspace) if workspace else candidate_workspace
        if home is None:
            (candidate_home / ("acp-" + mode + ".config.toml")).write_text(render_profile(mode))
        # Directory beneath the real workspace is the only live-target write.
        with tempfile.TemporaryDirectory(prefix=".acp-probe-", dir=selected_workspace) as inside:
            with socket.socket() as server:
                server.bind(("127.0.0.1", 0))
                server.listen(16)
                port = str(server.getsockname()[1])
                outside = root / "outside"
                outside.mkdir()
                tests = [("inside_write", "write", str(Path(inside) / "inside"),
                          "DENIED" if mode == "review" else "ALLOWED"),
                         ("outside_write", "write", str(outside / "outside"), "DENIED"),
                         ("command_network", "network", port, "DENIED")]
                checks = {}
                for label, operation, target, expected in tests:
                    command = [sys.executable, "-I", "-B", "-c", PROBE_CODE, operation, target]
                    # Positive control outside the Codex sandbox, including
                    # reachability before AND after the network denial attempt.
                    rc, out, _ = run(command, selected_home, selected_workspace)
                    if rc != 0 or out != b"START\nALLOWED\n":
                        checks[label] = "NOT_VERIFIED"
                        continue
                    if operation == "write":
                        Path(target).unlink()
                    rc, out, _ = run([str(binary), "sandbox", "--profile",
                                      "acp-" + mode, "--permission-profile", "acp-" + mode,
                                      "--cd", str(selected_workspace), "--", *command],
                                     selected_home, selected_workspace)
                    if rc != 0 or out not in (b"START\nALLOWED\n", b"START\nDENIED\n"):
                        checks[label] = "NOT_VERIFIED"
                    else:
                        checks[label] = "PASS" if out == f"START\n{expected}\n".encode() else "FAIL"
                    if operation == "network":
                        rc, out, _ = run(command, selected_home, selected_workspace)
                        if rc or out != b"START\nALLOWED\n":
                            checks[label] = "NOT_VERIFIED"
                status = ("FAIL" if "FAIL" in checks.values() else
                          "PASS" if all(v == "PASS" for v in checks.values()) else "NOT_VERIFIED")
                return {"status": status, "checks": checks, "scope": "local-command-sandbox",
                        "approval_ui": "NOT_RUN", "environment_filtering": "NOT_RUN",
                        "web_mcp_logs": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "plan", "apply", "verify", "rollback",
                                               "uninstall", "cleanup"))
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--codex", required=True, type=Path, help="Trusted native ELF binary, not npm shim")
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--plan-id")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup only")
    args = parser.parse_args()
    try:
        if (args.apply and args.operation != "cleanup") or (args.plan_id and args.operation != "apply"):
            raise Stop("INVALID_OPTIONS")
        manager = Manager(args.codex_home, args.workspace, args.codex, args.mode)
        if args.operation == "apply":
            if not args.plan_id or not re.fullmatch(r"[0-9a-f]{64}", args.plan_id):
                raise Stop("PLAN_ID_REQUIRED")
            result = manager.apply(args.plan_id)
        elif args.operation == "cleanup":
            result = manager.cleanup(args.apply)
        else:
            result = getattr(manager, args.operation)()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] in ("READY", "PASS", "APPLIED", "UNCHANGED", "RECOVERED",
                                         "RESTORED", "UNINSTALLED", "PREVIEW", "CLEANED") else 2
    except Stop as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
        return 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError, subprocess.SubprocessError):
        # Parser / OS / child errors may contain file content or sensitive paths.
        print('{"status":"BLOCKED","reason":"INPUT_OR_EXECUTION_UNAVAILABLE"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
