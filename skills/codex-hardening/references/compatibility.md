# Compatibility maintenance

## Stable intent, small version adapters

[recipes.json](../compatibility/recipes.json) holds exact tested versions,
OS/architecture, handler IDs, required CLI capabilities and references. It is
reviewed distribution data, never downloaded at runtime. It cannot contain
commands or executable expressions. The manager implements a finite set of
renderer/probe handlers and rejects unknown schema/handler IDs.

The default-protection adapters target exactly Codex 0.165.0 and 0.166.0 on Linux
x86_64. Historical 0.163.0/0.164.0 identification recipes remain, but new apply
and verify stop with `DEFAULT_PROTECTIONS_UNVERIFIED_VERSION` until rerun.
Its review profile extends `:read-only`; development adds workspace writes while
keeping `.git`, `.agents`, `.codex` and `.aws` read-only. General temporary paths
are not writable. Both disable command networking, select on-request approvals
with a human reviewer and disallow login shells. Read access is not confined to
the workspace: only the credential catalogue is denied; this is not a complete
secret-file confidentiality boundary.

An exact version match alone never establishes readiness. The native executable
identity and required help markers are checked, and apply must pass synthetic
probes. Unknown versions remain inspectable but cannot be applied. Same-version
replacement invalidates the plan fingerprint. No broad `>=` version promises.

## Initial conservative configuration boundary

The helper checks the user config, system and home managed-config locations,
every workspace ancestor's `.codex/config.toml`/hooks/rules and user hook/rule
files. It does not infer project trust or reproduce Codex's entire config resolver.
The selected Codex home's `config.toml` is classified as user configuration,
not registered again as project configuration when that home is also found in
the workspace's ancestry. This uses checked absolute paths, not symlink or
hardlink resolution. Distinct project files and overlapping managed, hook or
rule roles retain their existing review requirements; selecting a custom home
does not exempt a different ancestor `.codex/config.toml`.
For 0.163.0, existing project/managed layers, hook/rule files, security-model settings, feature
flags, telemetry or unrecognized top-level keys block automatic application.
This conservative superset can block a layer Codex would ignore; that is a
review request, not an invitation to remove it. Presence-only MCP/history/log
observations are not certification of those surfaces.

Handling those combinations later requires bounded, tested adapters. Do not add
an `--ignore-unknown` escape hatch. Broadening supported config is a code change
with tests, not a runtime agent interpretation or a web-derived rule injection.

### 0.164.0 bounded preferences adapter

The `preferences-v1` configuration policy replaces blanket project refusal only
for these keys. It preserves every file; it neither grants project trust nor
reproduces the effective layered configuration.

| Key | Accepted value |
| --- | --- |
| `model`, `model_reasoning_effort` | Printable, nonempty string, at most 256 characters |
| `model_reasoning_summary` | `auto`, `concise`, `detailed`, `none` |
| `model_verbosity` | `low`, `medium`, `high` |
| `hide_agent_reasoning` | Boolean |

String validation does not establish model availability or model-specific effort
support. These preferences cannot alter the local-command permission profile;
they are not a certification of model behavior or data handling.

Inspection reports redacted per-layer `configuration` entries with fixed reason
codes and `configuration_scope: local-command-policy`. `COMPATIBLE` permits
planning; `REVIEW_REQUIRED` and `CONFLICT` both block application. Project
permission, approval, login-shell or shell-environment overrides produce
`PROJECT_POLICY_OVERRIDE`; invalid preference values produce
`INVALID_PREFERENCE_VALUE`. Unknown project keys produce
`UNREVIEWED_PROJECT_KEYS`. Managed layers, hooks/rules and nonempty user feature
flags remain review blockers. Do not remove those controls merely to proceed.
All collected layers still participate in plan fingerprints and revalidation.
The 0.163.0 adapter remains conservative; unknown versions remain unsupported.

### 0.165.0 default protections

This adapter reuses `preferences-v1`, adds `protections: default-v1` and
`rules_policy: literal-v1`. It accepts only bounded literal prefix-rule syntax
after native validation, not arbitrary Starlark. See
[default-protections.md](default-protections.md) for credential groups,
exceptions, command-rule scope, existing allow warnings and runtime limits.
Both managed modes keep their original workspace/network permissions. New
credential denies require explicit user-home targeting; do not infer it from
Codex home. A workspace containing that home or inside a protected path blocks.
No binary was updated by the manager and no old runtime is silently accepted.

### 0.166.0 bounded user display/speed preferences

`user_preferences: display-v1` extends only the user layer, not project settings.
It preserves existing bytes and validates each nested field, rather than allowing
entire top-level tables. The 0.165.0 recipe retains its prior behavior: the old
binary was unavailable to certify this new adapter after an external update.

| Field | Accepted value |
| --- | --- |
| `features.fast_mode` | Boolean; no other feature flags are accepted by this adapter |
| `tui.status_line` | Array of at most 32 printable nonempty strings, each at most 256 characters |
| `tui.status_line_use_colors`, `tui.screen_reader_detection_done` | Boolean |
| `tui.session_picker_view` | `comfortable` or `dense` |
| `tui.resume_cwd` | `current` or `session`; resumed sessions are outside verification scope |
| `tui.model_availability_nux` | At most 128 entries; bounded printable names and uint32 values (not booleans) |
| `notice.fast_default_opt_out`, `notice.hide_rate_limit_model_nudge` | Boolean |
| `notice.model_migrations` | At most 128 bounded printable name/string pairs |

Map keys/strings have a 1–256 character bound and are never printed. Invalid types
produce `INVALID_USER_PREFERENCE` (CONFLICT). Unknown nested fields remain
REVIEW_REQUIRED, including warning-suppression keys not listed above. The helper
does not enable fast mode, change pricing, alter UI preferences or certify model
availability; it only preserves validated settings during profile management.

The same exact-version adapter now supports bounded coexistence metadata:

- `plugins`: up to 128 entries, each with only an optional Boolean `enabled`.
- `marketplaces`: up to 128 entries, with optional `source_type` (`git`/`local`),
  `source`, `ref`, `last_revision`, `last_updated` strings and `sparse_paths` list.
- Entry names are printable nonempty strings of at most 256 characters. Metadata
  strings are printable/nonempty and at most 4096 characters; sparse paths has
  at most 128 such strings. Empty tables are supported.

This is configuration compatibility, not executable trust or permission to fetch
a source. Unknown nested fields (including plugin MCP policy overlays) still
produce `PLUGIN_CONFIGURATION_REQUIRES_REVIEW` or
`MARKETPLACE_CONFIGURATION_REQUIRES_REVIEW`. Invalid types/limits produce
`INVALID_EXTENSION_METADATA` (CONFLICT). No plugin/source is opened, installed,
enabled, disabled or remotely contacted by inspection. No per-plugin approval
or ignore-unknown flag is added. Project-layer support is unchanged.

Reports expose fixed `scope_warnings`: `PLUGINS_NOT_VERIFIED`,
`MARKETPLACES_NOT_VERIFIED`, and `RESUMED_WORKSPACE_REQUIRES_REVALIDATION` when
applicable, without publishing names or source locations. They do not block an
otherwise compatible plan. Standard plan approval covers the proposed managed
changes, not certification of these external surfaces. All configuration bytes
remain fingerprinted; metadata changes invalidate a pending plan.

`tui.resume_cwd = "session"` is preserved. `verification_scope` limits profile
evidence to the selected workspace/profile and a new-session workflow. A resumed
session, different workspace or launch override must not inherit that evidence.
The manager does not intercept launches or enforce revalidation automatically.

Sources: [official reference](https://learn.chatgpt.com/docs/config-file/config-reference)
and [official schema](https://developers.openai.com/codex/config-schema.json),
checked on 2026-11-01 and 2026-11-03. These are moving documents, not version-pinned source.
Native 0.166.0 synthetic lifecycle/negative-parser checks supplement them; live
interactive TUI behavior, resumption and plugin execution are not certified.

## Updating support

1. Obtain the requested release through an independently approved process. This
   skill never upgrades/downgrades Codex or changes credentials automatically.
2. Review official release notes, version-matched source/schema when available,
   current docs and local CLI help. Record provenance, revision/digest and date
   in validation evidence. Schema validity does not prove runtime enforcement.
3. Run existing fixtures and real probes against the trusted native binary. A
   failure may be an interface change, behavior regression or host limitation;
   classify it before editing settings.
4. Reuse a handler when behavior is unchanged. If not, add the smallest explicit
   handler and reproducer. Preserve the stable intent tests.
5. Re-run every version/OS still advertised as tested. Record unavailable binaries
   as NOT RUN; do not claim mocked versions are runtime-certified.
6. Add the exact tested version to a recipe only after evidence. Distribute the
   reviewed skill update. At each deployment, re-run inspect/plan/apply/verify.

Fingerprint inputs include executable bytes/path, related configuration files,
profile/state, compatibility definition, script, Python identity, OS, UID and
workspace/home. Verification is never cached; it rechecks before and after
probes and rejects drift. No continuous monitor or mandatory launch wrapper is
installed. A caller that does not run this manager is not stopped by it.

## References and observed differences

- [Official configuration layering](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [Official permission profiles](https://learn.chatgpt.com/docs/permissions)
- [Official approval/sandbox guidance](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Official execution rules](https://learn.chatgpt.com/docs/agent-configuration/rules)

The installed 0.163.0 sandbox CLI requires `--permission-profile` when selecting
a config profile and rejects `--strict-config` for `sandbox`. Real initial
tests exposed both cases; neither was treated as a successful policy denial.
Use actual handler tests instead of assuming every global CLI flag is supported
by every subcommand. Consult validation evidence for the tested binary digest.
