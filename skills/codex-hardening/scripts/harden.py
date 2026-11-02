"""Manage narrowly scoped Codex hardening profiles (Python 3.11+, Linux).

No shell, network downloads, model calls, credential reads or base-config writes.
The local account, trusted native Codex binary and this skill are trust anchors.
"""
import argparse
import ast
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
# Exact default locations, not a recursive credential search. Never open these
# paths while inspecting or rendering a policy. Custom locations need review.
CREDENTIAL_PATHS = {
    "ssh": (".ssh",), "aws": (".aws",), "gcloud": (".config/gcloud",),
    "azure": (".azure",), "oci": (".oci",), "kubernetes": (".kube",),
    "docker": (".docker/config.json",), "containers": (".config/containers/auth.json",),
    "terraform": (".terraform.d/credentials.tfrc.json", ".terraformrc"),
    "pulumi": (".pulumi/credentials.json",), "vault": (".vault-token",),
    "github": (".config/gh/hosts.yml",), "gitlab": (".config/glab-cli/config.yml",),
    "git": (".git-credentials", ".config/git/credentials"),
    "npm": (".npmrc",), "pypi": (".pypirc",),
    "netrc": (".netrc",), "cargo": (".cargo/credentials", ".cargo/credentials.toml"),
    "gem": (".gem/credentials",), "gnupg": (".gnupg",),
    "database": (".pgpass", ".my.cnf", ".mylogin.cnf"),
}
COMMAND_CONTROLS = ("sudo", "rm")


def exceptions(values, allowed):
    if not isinstance(values, (tuple, list)) or any(type(v) is not str or v not in allowed for v in values):
        raise Stop("UNKNOWN_PROTECTION_EXCEPTION")
    return tuple(sorted(set(values)))


def literal_rules(data):
    """Accept only bounded literal prefix_rule calls. Never eval/exec Starlark."""
    try:
        tree = ast.parse(data.decode("utf-8"))
        if sum(1 for _ in ast.walk(tree)) > 20000 or len(tree.body) > 200:
            raise ValueError()
        result = []
        for statement in tree.body:
            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                raise ValueError()
            call = statement.value
            if not isinstance(call.func, ast.Name) or call.func.id != "prefix_rule" or call.args:
                raise ValueError()
            fields = {}
            for kw in call.keywords:
                if kw.arg not in ("pattern", "decision", "justification", "match", "not_match") or kw.arg in fields:
                    raise ValueError()
                fields[kw.arg] = ast.literal_eval(kw.value)
            pattern = fields.get("pattern")
            def word(value):
                return type(value) is str and 0 < len(value) <= 4096 and value.isprintable()
            if not isinstance(pattern, list) or not 1 <= len(pattern) <= 64:
                raise ValueError()
            if any(not word(v) and not (isinstance(v, list) and 1 <= len(v) <= 64
                                        and all(word(w) for w in v)) for v in pattern):
                raise ValueError()
            if fields.get("decision", "allow") not in ("allow", "prompt", "forbidden"):
                raise ValueError()
            if "justification" in fields and not word(fields["justification"]):
                raise ValueError()
            for key in ("match", "not_match"):
                if key in fields and (not isinstance(fields[key], list) or len(fields[key]) > 200
                                       or not all(word(v) for v in fields[key])):
                    raise ValueError()
            result.append(fields)
        return result
    except (UnicodeError, SyntaxError, ValueError, TypeError, RecursionError):
        raise Stop("UNREVIEWED_RULE_SYNTAX") from None


def render_rules(disabled=(), user_home=None):
    disabled = exceptions(disabled, COMMAND_CONTROLS)
    lines = ["# Managed by codex-hardening; applies to this entire Codex home.",
             "# Disabled protections: " + (", ".join(disabled) or "none")]
    for control, decision in (("sudo", "forbidden"), ("rm", "prompt")):
        if control not in disabled:
            pattern = [[control, "/bin/" + control, "/usr/bin/" + control]]
            lines.append(f"prefix_rule(pattern={json.dumps(pattern)}, decision={json.dumps(decision)})")
    if "rm" not in disabled:
        roots = ["/"] + ([str(user_home)] if user_home is not None else [])
        for flags in (["-rf"], ["-fr"], ["-r"], ["-R"], ["-f", "-r"],
                      ["-r", "-f"], ["--recursive", "--force"]):
            for separator in ([], ["--"]):
                pattern = [["rm", "/bin/rm", "/usr/bin/rm"], *flags, *separator, roots]
                lines.append(f'prefix_rule(pattern={json.dumps(pattern)}, decision="forbidden")')
    return "\n".join(lines) + "\n"
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
PREFERENCE_KEYS = {"model", "model_reasoning_effort", "model_reasoning_summary",
                   "model_verbosity", "hide_agent_reasoning"}
PERMISSION_KEYS = {"sandbox_mode", "sandbox_workspace_write", "permissions", "default_permissions"}
PROJECT_POLICY_KEYS = PERMISSION_KEYS | {"approval_policy", "approvals_reviewer",
                                         "allow_login_shell", "shell_environment_policy"}
CONFIG_CONFLICTS = {"PERMISSION_MODEL_CONFLICT", "PROJECT_POLICY_OVERRIDE", "INVALID_PREFERENCE_VALUE",
                    "INVALID_USER_PREFERENCE", "INVALID_EXTENSION_METADATA"}
USER_PREFERENCE_GROUPS = {"tui", "notice"}
TUI_FIELDS = {"status_line", "status_line_use_colors", "screen_reader_detection_done",
              "session_picker_view", "resume_cwd", "model_availability_nux"}
NOTICE_FIELDS = {"fast_default_opt_out", "hide_rate_limit_model_nudge", "model_migrations"}
# Diagnostic vocabulary only, NOT permission to accept these settings. Never
# echo arbitrary keys: TOML names can themselves contain private data.
REVIEW_KEY_NAMES = {"tui", "notice", "plugins", "apps", "skills", "agents",
                    "model_provider", "model_providers", "notify", "profile", "profiles", "marketplaces"}
REVIEW_FEATURE_NAMES = {"fast_mode", "multi_agent", "apps", "hooks", "memories",
                        "remote_plugin", "shell_snapshot", "unified_exec", "network_proxy"}


def configuration_review_details(config, kind, user_policy=None):
    allowed = PREFERENCE_KEYS | PROJECT_POLICY_KEYS if kind == "project" else KNOWN_KEYS
    if kind == "user" and user_policy == "display-v1":
        allowed = allowed | USER_PREFERENCE_GROUPS
    unknown = set(config) - allowed
    features = config.get("features", {})
    return {
        "recognized_unreviewed_keys": sorted(unknown & REVIEW_KEY_NAMES),
        "unknown_key_count": len(unknown - REVIEW_KEY_NAMES),
        "recognized_features": sorted(set(features) & REVIEW_FEATURE_NAMES) if isinstance(features, dict) else [],
        "unknown_feature_count": len(set(features) - REVIEW_FEATURE_NAMES) if isinstance(features, dict) else 0,
        "feature_shape": "TABLE" if isinstance(features, dict) else "INVALID",
    }


def review_next_steps(issues):
    steps = []
    if "FEATURE_FLAGS_REQUIRE_REVIEW" in issues:
        steps.append("Review feature names against the tested CLI version; add a bounded adapter and tests before accepting them.")
    if {"UNREVIEWED_CONFIG_KEYS", "UNREVIEWED_PROJECT_KEYS"} & set(issues):
        steps.append("Review recognized setting groups separately; plugin/tool policy is not a display preference. Unknown names and all values stay private; inspect them locally, not in shared logs.")
    if {"PLUGIN_CONFIGURATION_REQUIRES_REVIEW", "MARKETPLACE_CONFIGURATION_REQUIRES_REVIEW"} & set(issues):
        steps.append("Extension fields exceed the bounded metadata adapter; review their authority impact and add tested support. Do not delete settings to bypass inspection.")
    if "INVALID_EXTENSION_METADATA" in issues:
        steps.append("Check documented extension metadata types and limits locally; names, sources and values are not printed.")
    if {"UNREVIEWED_TUI_KEYS", "UNREVIEWED_NOTICE_KEYS", "INVALID_USER_PREFERENCE"} & set(issues):
        steps.append("Check the documented bounded user-preference fields and types locally; unknown nested fields remain unsupported, not silently discarded.")
    if issues:
        steps.append("Preserve existing configuration. Resolve the reported compatibility blockers, then rerun inspect and plan; do not delete settings or switch homes to bypass checks.")
    return steps


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


def extension_metadata_issues(config):
    """Parse metadata, not plugin code or trust. Never open/fetch a source."""
    issues = []
    fields = {"plugins": {"enabled"},
              "marketplaces": {"source_type", "source", "ref", "last_revision",
                               "last_updated", "sparse_paths"}}
    def text(value, limit=4096):
        return type(value) is str and 0 < len(value) <= limit and value.isprintable()

    for section, allowed in fields.items():
        table = config.get(section, {})
        if not isinstance(table, dict) or len(table) > 128:
            issues.append("INVALID_EXTENSION_METADATA")
            continue
        for name, entry in table.items():
            if not text(name, 256) or not isinstance(entry, dict):
                issues.append("INVALID_EXTENSION_METADATA")
                continue
            if set(entry) - allowed:
                issues.append("PLUGIN_CONFIGURATION_REQUIRES_REVIEW" if section == "plugins"
                              else "MARKETPLACE_CONFIGURATION_REQUIRES_REVIEW")
            for key in set(entry) & allowed:
                value = entry[key]
                if key == "enabled":
                    valid = type(value) is bool
                elif key == "source_type":
                    valid = type(value) is str and value in ("git", "local")
                elif key == "sparse_paths":
                    valid = isinstance(value, list) and len(value) <= 128 and all(text(v) for v in value)
                else:
                    valid = text(value)
                if not valid:
                    issues.append("INVALID_EXTENSION_METADATA")
    return sorted(set(issues))


def user_preference_issues(config):
    """Version-gated typed preferences only; never interpret plugin metadata."""
    issues = []
    def text(value):
        return type(value) is str and 0 < len(value) <= 256 and value.isprintable()

    for section, fields in (("features", {"fast_mode"}), ("tui", TUI_FIELDS), ("notice", NOTICE_FIELDS)):
        table = config.get(section, {})
        if not isinstance(table, dict):
            issues.append("INVALID_USER_PREFERENCE")
            continue
        if set(table) - fields:
            issues.append("FEATURE_FLAGS_REQUIRE_REVIEW" if section == "features" else
                          "UNREVIEWED_" + section.upper() + "_KEYS")
        for key in set(table) & fields:
            value = table[key]
            if key in {"fast_mode", "status_line_use_colors", "screen_reader_detection_done",
                       "fast_default_opt_out", "hide_rate_limit_model_nudge"}:
                valid = type(value) is bool
            elif key == "status_line":
                valid = isinstance(value, list) and len(value) <= 32 and all(text(v) for v in value)
            elif key == "session_picker_view":
                valid = type(value) is str and value in ("comfortable", "dense")
            elif key == "resume_cwd":
                valid = type(value) is str and value in ("current", "session")
            else:  # Bounded UI state maps; keys/values never reach diagnostics.
                valid = isinstance(value, dict) and len(value) <= 128 and all(
                    text(k) and (text(v) if key == "model_migrations" else
                                 type(v) is int and 0 <= v <= 2**32 - 1)
                    for k, v in value.items())
            if not valid:
                issues.append("INVALID_USER_PREFERENCE")
    return sorted(set(issues))


def configuration_issues(config, kind, policy, user_policy=None):
    """Classify a bounded parsed layer; return only fixed reason codes."""
    issues = []
    if kind == "project":
        if set(config) & PROJECT_POLICY_KEYS:
            issues.append("PROJECT_POLICY_OVERRIDE")
        if set(config) - PREFERENCE_KEYS - PROJECT_POLICY_KEYS:
            issues.append("UNREVIEWED_PROJECT_KEYS")
    else:
        display = kind == "user" and user_policy == "display-v1"
        extra = USER_PREFERENCE_GROUPS | {"plugins", "marketplaces"} if display else set()
        if set(config) - KNOWN_KEYS - extra:
            issues.append("UNREVIEWED_CONFIG_KEYS")
        if set(config) & PERMISSION_KEYS:
            issues.append("PERMISSION_MODEL_CONFLICT")
        if display:
            issues.extend(user_preference_issues(config))
            issues.extend(extension_metadata_issues(config))
        elif config.get("features"):
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
    if policy == "preferences-v1":
        enums = {"model_reasoning_summary": ("auto", "concise", "detailed", "none"),
                 "model_verbosity": ("low", "medium", "high")}
        for key in PREFERENCE_KEYS & set(config):
            value = config[key]
            if key == "hide_agent_reasoning":
                valid = type(value) is bool
            elif key in enums:
                valid = type(value) is str and value in enums[key]
            else:
                valid = type(value) is str and 0 < len(value) <= 256 and value.isprintable()
            if not valid:
                issues.append("INVALID_PREFERENCE_VALUE")
    return sorted(set(issues))


def render_profile(mode, disabled=(), user_home=None):
    if mode not in MODES:
        raise Stop("UNKNOWN_MODE")
    access = "read" if mode == "review" else "write"
    name = "acp-" + mode
    disabled = exceptions(disabled, CREDENTIAL_PATHS)
    base = str(user_home) if user_home is not None else "~"
    denied = "".join(f'{json.dumps(base + "/" + path)} = "deny"\n'
                     for group, paths in CREDENTIAL_PATHS.items() if group not in disabled for path in paths)
    return (
        '# Managed by codex-hardening. Select explicitly; not a global policy.\n'
        '# Disabled protections: ' + (", ".join(disabled) or "none") + '\n' +
        f'default_permissions = "{name}"\n'
        'approval_policy = "on-request"\n'
        'approvals_reviewer = "user"\n'
        'allow_login_shell = false\n'
        f'\n[permissions.{name}]\n'
        'extends = ":read-only"\n'
        f'\n[permissions.{name}.filesystem]\n' + denied +
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
            if recipe.get("config_policy", "conservative-v1") not in ("conservative-v1", "preferences-v1"):
                raise Stop("RECIPE_HANDLER_UNSUPPORTED")
            if recipe.get("protections") not in (None, "default-v1") or recipe.get("rules_policy") not in (None, "literal-v1"):
                raise Stop("RECIPE_HANDLER_UNSUPPORTED")
            if recipe.get("user_preferences") not in (None, "display-v1"):
                raise Stop("RECIPE_HANDLER_UNSUPPORTED")
            commands = {"root": ["--help"], "sandbox": ["sandbox", "--help"],
                        "rules": ["execpolicy", "check", "--help"]}
            for key, markers in recipe["required_help"].items():
                rc, output, _ = run([str(binary), *commands[key]], temporary, temporary)
                if rc or any(marker.encode() not in output for marker in markers):
                    raise Stop("CLI_CAPABILITY_MISMATCH")
    return identity, version, recipe


class Manager:
    def __init__(self, home, workspace, binary, mode, disabled=(), user_home=None):
        self.home = checked_path(home, directory=True)
        self.workspace = checked_path(workspace, directory=True)
        self.binary = checked_path(binary)
        if mode not in (*MODES, "command-rules"):
            raise Stop("UNKNOWN_MODE")
        self.mode = mode
        self.disabled = exceptions(disabled, COMMAND_CONTROLS if mode == "command-rules" else CREDENTIAL_PATHS)
        # CLI requires an explicit user home. Programmatic isolated callers use
        # their fixture Codex home by default, never the operator's HOME.
        self.user_home = checked_path(user_home or home, directory=True)
        self.name = "acp-" + mode
        self.target = self.home / (self.name + ".config.toml")
        if mode == "command-rules":
            self.target = self.home / "rules" / "acp-hardening.rules"
        self.directory = self.home / STATE_DIR
        self.state_path = self.directory / (mode + ".json")
        self.journal = self.directory / (mode + ".pending.json")

    def candidate(self):
        return (render_rules(self.disabled, self.user_home) if self.mode == "command-rules" else
                render_profile(self.mode, self.disabled, self.user_home))

    def layers(self):
        # Conservative superset: inspect every ancestor instead of guessing the
        # repo/trust boundary. System/managed layers need a separate adapter.
        user_config = self.home / "config.toml"
        paths = [(user_config, "user")]
        for name in ("config.toml", "requirements.toml", "managed_config.toml"):
            paths.append((Path("/etc/codex") / name, "managed"))
        for name in ("requirements.toml", "managed_config.toml"):
            paths.append((self.home / name, "managed"))
        for parent in reversed((self.workspace, *self.workspace.parents)):
            project_config = parent / ".codex" / "config.toml"
            # Checked absolute paths identify the selected user config, even
            # when the workspace is beneath HOME. Do not reclassify it as a
            # project layer, resolve aliases, or suppress other managed roles.
            if project_config != user_config:
                paths.append((project_config, "project"))
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
        # Identical hook/rule roles can also overlap home/workspace traversal.
        return list(dict.fromkeys(paths))

    def inspect(self):
        identity, version, recipe = detect(self.binary)
        issues, fingerprints, observations, classifications = [], {}, {}, []
        scope_warnings = []
        policy = recipe.get("config_policy", "conservative-v1") if recipe else "conservative-v1"
        if not recipe:
            issues.append("UNSUPPORTED_VERSION_OR_PLATFORM")
        elif recipe.get("protections") != "default-v1":
            issues.append("DEFAULT_PROTECTIONS_UNVERIFIED_VERSION")
        if self.mode != "command-rules":
            if self.user_home.is_relative_to(self.workspace):
                issues.append("WORKSPACE_CONTAINS_USER_HOME")
            for group, paths in CREDENTIAL_PATHS.items():
                if group not in self.disabled and any(self.workspace.is_relative_to(self.user_home / p) for p in paths):
                    issues.append("WORKSPACE_OVERLAPS_PROTECTED_PATH")
        layers = self.layers()
        if len(layers) > 400:
            raise Stop("INPUT_LIMIT")
        total = 0
        rule_allows = 0
        for path, kind in layers:
            if path == self.target and self.mode == "command-rules":
                continue  # Managed target has independent ownership/drift checks.
            data = read_file(path)
            total += len(data) if data else 0
            if total > 8 * MAX_FILE:
                raise Stop("INPUT_LIMIT")
            fingerprints[str(path)] = None if data is None else digest(data)
            if data is None:
                continue
            review_details = None
            if kind == "rules" and recipe and recipe.get("rules_policy") == "literal-v1":
                try:
                    parsed_rules = literal_rules(data)
                    rule_allows += sum(v.get("decision", "allow") == "allow" for v in parsed_rules)
                    layer_issues = [] if validate_rules(self.binary, [data]) else ["INVALID_NATIVE_RULES"]
                except Stop as error:
                    layer_issues = [str(error)]
            elif kind in ("managed", "hooks", "rules") or (kind == "project" and policy != "preferences-v1"):
                # Do not evaluate arbitrary rule text or start project hooks.
                layer_issues = ["REVIEW_REQUIRED_" + kind.upper()]
            else:
                config = parse_toml(data)
                user_policy = recipe.get("user_preferences") if recipe else None
                layer_issues = configuration_issues(config, kind, policy, user_policy)
                if layer_issues:
                    review_details = configuration_review_details(config, kind, user_policy)
            status = ("CONFLICT" if CONFIG_CONFLICTS & set(layer_issues) else
                      "REVIEW_REQUIRED" if layer_issues else "COMPATIBLE")
            classification = {"layer": kind, "status": status, "reasons": layer_issues}
            if review_details is not None:
                classification["review_details"] = review_details
            classifications.append(classification)
            issues.extend(layer_issues)
            if kind != "user":
                continue
            # All counts / enums, never user-supplied names, URLs or values.
            for key in ("mcp_servers", "otel", "memories", "shell_environment_policy", "log_dir",
                        "plugins", "marketplaces"):
                observations[key] = "configured" if key in config else "not_explicit"
            for key in ("plugins", "marketplaces"):
                if key in config:
                    scope_warnings.append(key.upper() + "_NOT_VERIFIED")
            tui = config.get("tui", {})
            if isinstance(tui, dict) and tui.get("resume_cwd") == "session":
                scope_warnings.append("RESUMED_WORKSPACE_REQUIRES_REVALIDATION")
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
                    "user_home": str(self.user_home), "disabled": self.disabled,
                    "files": fingerprints, "state": state,
                    "recipe_digest": digest(read_file(RECIPES)),
                    "script_digest": digest(read_file(Path(__file__))),
                    "python": {"path": sys.executable, "version": sys.version},
                    "platform": platform.platform(), "uid": os.getuid()}
        return {"status": "READY" if not issues else "BLOCKED",
                "version": version, "recipe": recipe["id"] if recipe else None,
                "issues": sorted(set(issues)), "next_steps": review_next_steps(issues), "observations": observations,
                "configuration": classifications, "configuration_scope": "local-command-policy",
                "verification_scope": ("native-command-decisions-only" if self.mode == "command-rules" else
                                       "selected-workspace-and-profile; new-session-only"),
                "scope_warnings": sorted(set(scope_warnings)),
                "disabled_protections": list(self.disabled),
                "existing_rule_allow_count": rule_allows,
                "rule_warning": "existing allows can execute outside filesystem protections" if rule_allows else None,
                "installation_scope": "codex-home-wide" if self.mode == "command-rules" else "selected-profile",
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
        if len(self.candidate()) > 8192:
            raise Stop("CANDIDATE_LIMIT")
        # Preview uses a symbolic home; actual bytes use the explicit absolute
        # user home. Bind those bytes without exposing private path names.
        report["candidate"] = (render_rules(self.disabled, "~") if self.mode == "command-rules"
                               else render_profile(self.mode, self.disabled))
        report["candidate_sha256"] = digest(self.candidate().encode())
        report["candidate_home"] = "~ denotes the explicit --user-home, not --codex-home"
        report["applicable"] = report["status"] == "READY"
        report["candidate_status"] = "REQUIRES_APPROVAL" if report["applicable"] else "REFERENCE_ONLY"
        report["plan_id"] = digest(encoded(report)) if report["applicable"] else None
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
            if self.mode == "command-rules":
                checked_path(self.target.parent)
                self.target.parent.mkdir(mode=0o700, exist_ok=True)
                info = self.target.parent.stat()
                if info.st_uid != os.getuid() or info.st_mode & 0o022:
                    raise Stop("UNSAFE_RULE_DIRECTORY")
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
            if state and state["current"] == self.candidate():
                return {"status": "UNCHANGED", "runtime": "NOT_VERIFIED",
                        "other_surfaces": "NOT_VERIFIED", "scope_warnings": plan["scope_warnings"],
                        "verification_scope": plan["verification_scope"]}
            # Candidate verification uses no original config or secrets.
            result = self.check_candidate()
            if result["status"] != "PASS":
                result.update(other_surfaces="NOT_VERIFIED", scope_warnings=plan["scope_warnings"],
                              verification_scope=plan["verification_scope"])
                return result
            if self.plan()["plan_id"] != plan_id:
                raise Stop("STALE_PLAN")
            result = self.transition(state, self.candidate())
            result.update(other_surfaces="NOT_VERIFIED", scope_warnings=plan["scope_warnings"],
                          verification_scope=plan["verification_scope"])
            return result

    def check_candidate(self, live=False):
        if self.mode == "command-rules":
            existing = [read_file(path) for path, kind in self.layers()
                        if kind == "rules" and path != self.target]
            return rules_probe(self.binary, self.candidate().encode(), [v for v in existing if v], self.disabled, self.user_home)
        result = probe(self.binary, self.mode, self.home if live else None,
                       self.workspace if live else None, disabled=self.disabled)
        if result["status"] == "PASS":
            credentials = credential_probe(self.binary, self.mode, self.disabled)
            result["credential_fixture"] = credentials["status"]
            result["credential_scope"] = "synthetic-default-paths; live credentials never opened"
            if credentials["status"] != "PASS":
                result["status"] = credentials["status"]
        return result

    def verify(self):
        before = self.inspect()
        if before["status"] != "READY" or read_file(self.target) != self.candidate().encode():
            raise Stop("VERIFY_PRECONDITION_FAILED")
        result = self.check_candidate(live=True)
        after = self.inspect()
        if before["fingerprint"] != after["fingerprint"]:
            raise Stop("ENVIRONMENT_CHANGED_DURING_VERIFY")
        result["fingerprint"] = after["fingerprint"]
        # No persisted PASS cache: verify always re-runs. This prevents a stale
        # local receipt from becoming an authorization or startup bypass.
        result["other_surfaces"] = "NOT_VERIFIED"
        result["scope_warnings"] = after["scope_warnings"]
        result["verification_scope"] = after["verification_scope"]
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


def probe(binary, mode, home=None, workspace=None, disabled=()):
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
            (candidate_home / ("acp-" + mode + ".config.toml")).write_text(render_profile(mode, disabled))
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


def rule_decision(binary, blobs, command):
    with tempfile.TemporaryDirectory(prefix="codex-hardening-rules-") as temporary:
        root = Path(temporary)
        args = [str(binary), "execpolicy", "check"]
        for index, blob in enumerate(blobs):
            literal_rules(blob)
            path = root / (str(index) + ".rules")
            path.write_bytes(blob)
            args.extend(["--rules", str(path)])
        rc, output, _ = run([*args, "--", *command], root, root)
        try:
            report = json.loads(output)
            if rc or not isinstance(report, dict):
                raise ValueError()
            decision = report.get("decision", "none")
            if decision not in ("allow", "prompt", "forbidden", "none"):
                raise ValueError()
            return decision
        except (ValueError, TypeError):
            raise Stop("NATIVE_RULE_VALIDATION_FAILED") from None


def validate_rules(binary, blobs):
    rule_decision(binary, blobs, ["acp-inert-rule-validation"])
    return True


def rules_probe(binary, candidate, existing, disabled, user_home=None):
    checks = {}
    commands = []
    if "sudo" not in disabled:
        commands.extend(("sudo", [name, "true"], "forbidden")
                        for name in ("sudo", "/bin/sudo", "/usr/bin/sudo"))
    if "rm" not in disabled:
        commands.extend(("rm", [name, "-rf", "acp-synthetic-target"], "prompt")
                        for name in ("rm", "/bin/rm", "/usr/bin/rm"))
        commands.append(("rm-root", ["rm", "-rf", "/"], "forbidden"))
        if user_home is not None:
            commands.append(("rm-home", ["rm", "-rf", str(user_home)], "forbidden"))
    validate_rules(binary, [*existing, candidate])
    for index, (label, command, expected) in enumerate(commands):
        observed = rule_decision(binary, [*existing, candidate], command)
        # Existing stricter rules remain valid; no opt-out removes their policy.
        checks[f"{label}-{index}"] = ("PASS" if observed == expected or
                                      (expected == "prompt" and observed == "forbidden") else "FAIL")
    return {"status": "PASS" if all(v == "PASS" for v in checks.values()) else "FAIL",
            "checks": checks, "scope": "native-execpolicy-decisions",
            "approval_ui": "NOT_RUN", "command_execution": "NOT_RUN"}


def credential_probe(binary, mode, disabled):
    # Never inspect real credential existence/content or write in real stores.
    with tempfile.TemporaryDirectory(prefix="codex-hardening-credentials-") as temporary:
        root = Path(temporary)
        home, work = root / "home", root / "work"
        home.mkdir()
        work.mkdir()
        directories = {"ssh", "aws", "gcloud", "azure", "oci", "kubernetes", "gnupg"}
        cases = []
        for group, paths in CREDENTIAL_PATHS.items():
            for relative in paths:
                path = home / relative
                if group in directories:
                    path = path / "fixture"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"inert fixture")
                cases.append((str(path), "ALLOWED" if group in disabled else "DENIED"))
        (home / ("acp-" + mode + ".config.toml")).write_text(render_profile(mode, disabled, home))
        code = '''import errno,json,sys
results=[]
for path in json.loads(sys.argv[1]):
    try:
        with open(path, "rb"):
            pass
    except OSError as error:
        results.append("DENIED" if error.errno in (errno.EACCES, errno.EPERM) else "INCOMPLETE")
    else:
        results.append("ALLOWED")
print(json.dumps(results))
'''
        command = [sys.executable, "-I", "-B", "-c", code, json.dumps([p for p, _ in cases])]
        rc, out, _ = run(command, home, work)
        if rc or json.loads(out) != ["ALLOWED"] * len(cases):
            return {"status": "NOT_VERIFIED"}
        rc, out, _ = run([str(binary), "sandbox", "--profile", "acp-" + mode,
                          "--permission-profile", "acp-" + mode, "--cd", str(work), "--", *command], home, work)
        try:
            observed = json.loads(out)
        except ValueError:
            return {"status": "NOT_VERIFIED"}
        return {"status": "PASS" if rc == 0 and observed == [v for _, v in cases] else "FAIL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "plan", "apply", "verify", "rollback",
                                               "uninstall", "cleanup"))
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--codex", required=True, type=Path, help="Trusted native ELF binary, not npm shim")
    parser.add_argument("--mode", required=True, choices=(*MODES, "command-rules"))
    parser.add_argument("--user-home", required=True, type=Path, help="Explicit OS user home; not Codex home")
    parser.add_argument("--disable-protection", action="append", default=[],
                        help="Named opt-out; repeat per credential group, or sudo/rm in command-rules mode")
    parser.add_argument("--plan-id")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup only")
    args = parser.parse_args()
    try:
        if (args.apply and args.operation != "cleanup") or (args.plan_id and args.operation != "apply"):
            raise Stop("INVALID_OPTIONS")
        manager = Manager(args.codex_home, args.workspace, args.codex, args.mode,
                          args.disable_protection, args.user_home)
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
