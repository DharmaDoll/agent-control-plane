# Operations

## Choose a scene

No manually authored profile is a prerequisite. The manager already contains
two deterministic templates; select a scene and generate its local profile
after inspection and approval.

| Scene | Mode / session profile | Intended use | Important limits |
| --- | --- | --- | --- |
| Investigation | `review` / `acp-review` | Read code and investigate findings | No workspace writes; sandboxed command networking disabled |
| Development | `development` / `acp-development` | Edit code and run local tests | Protected metadata stays read-only; no general temporary-directory writes or sandboxed command networking |

Both include the default credential-path protections. Development is the normal
recommendation for editing, not a claim that dependency downloads, push, Docker
or every build work without additional authorization. Neither preset is a
complete isolation environment for hostile code. Do not add an untested
"restricted" or network-enabled preset merely to fill a menu.

First-time workflow:

1. Establish the installation and target paths below, inspect, and explain any
   blocker. Do not require the user to know profile names or write TOML.
2. Offer the two scenes with their limits, unless the user already chose one.
3. Plan the selected preset with default protections, or explicitly approved
   named exceptions. Explain the candidate and its target before applying it.
4. Apply the accepted plan and verify. Present the matching new-session command.
   Installation does not change the global default or the current session.

The templates are portable; generated files are not: credential paths, supported
CLI version and verification evidence depend on the target environment. Do not
copy a finished profile from another machine. Creating both presets is optional
and requires independent plans and verification, not an implicit batch install.
If only one succeeds, report the other as incomplete without undoing unrelated
successful work.

For a later scene switch, verify the installed preset for the intended workspace
with its approved exceptions, then start a new session with `--profile acp-review`
or `--profile acp-development`. A missing preset follows first-time setup.
To change exceptions, run a fresh plan/apply/verify cycle for that preset; repeat
the complete intended exception list. Do not treat a switch as permission to
reset exceptions, edit base settings or change home-wide command rules.

The optional `command-rules` installation is a separate common layer, not a
third scene. It requires its own scope-specific approval and does not require a
profile to exist. Switching profiles does not disable these home-wide rules.

## Prerequisites and target

Use an existing Python 3.11+ interpreter; never install one implicitly. Pass the
absolute native Codex ELF binary, not the `codex` npm shell/JavaScript launcher.
The manager hashes that executable rather than mistaking an unchanged launcher
for an unchanged runtime. Paths with symlink components are rejected; establish
and explicitly supply the intended canonical path after checking the layout.
This is change detection, not vendor signature or provenance verification.

Select an existing absolute Codex home and workspace. Do not use a repository's
`.codex/` directory as a substitute for the user's Codex home. Each command uses
the same explicit target arguments:

```sh
python3.11 -I -B <skill-dir>/scripts/harden.py inspect \
  --codex /absolute/native/codex \
  --codex-home /absolute/codex-home \
  --user-home /absolute/os-user-home \
  --workspace /absolute/repository \
  --mode development
```

Replace `inspect` with `plan` for the candidate. After reviewing its scope, use
`apply` with the same arguments plus `--plan-id <reported-plan-id>`. Then run
`verify` with the same arguments. `review` is the other profile mode. Use
`command-rules` for the separate home-wide command rule installation. Read
[default-protections.md](default-protections.md) before selecting that scope or
adding a named `--disable-protection` exception. Repeat exceptions for plan,
apply and verify; never infer exceptions from an execution failure.

`inspect` and `plan` leave the target unchanged. They parse bounded config files
and run version/help checks in a temporary synthetic home with a minimal
environment. They never load `auth.json` or enumerate session/log contents.

## Files and selection

The only managed profiles are:

- `<codex-home>/acp-review.config.toml`
- `<codex-home>/acp-development.config.toml`

The separate rules target is `<codex-home>/rules/acp-hardening.rules`, with its
own command-rules state/journal and the same shared lock/recovery mechanism.
Other rule files are never rewritten. Uninstall retains the directory and
unrelated files. Rules affect other sessions using this home; restart Codex
after changes. Profile uninstall does not remove command-rules, or vice versa.

State and a permanent advisory lock live in `<codex-home>/codex-hardening-state/`.
Records contain current/previous **generated** profile text, not copies of base
config or credentials. Profiles/records are mode 0600; state directory is 0700.
Plans show a symbolic `~` instead of the explicit user home. Installed bytes use
absolute paths and are hashed as `candidate_sha256`; they record disabled IDs.
An unowned or group/world-writable management home is rejected for mutations.

The generated configuration defines a permission profile of the same name. For
a **new** session with the inspected Codex home, select it explicitly:

```sh
codex --profile acp-development --cd /absolute/repository
```

The `codex` used here must resolve to the tested installation. Ensure its actual
Codex home is the inspected home. Do not add sandbox, permission, configuration,
workspace-root, remote-server or approval overrides and assume the same evidence
still applies. Different launch settings and live sessions need separate checks.
This example is not a request for the skill to launch a model session.

## Result contract

- `READY`: recognized recipe and inspectable, non-conflicting configuration.
- `PASS` / `FAIL`: observed local-command probe results, not global security.
- `NOT_VERIFIED`: probe startup/control/protocol failure or unavailable evidence.
- `BLOCKED`: precondition, unsupported version/configuration, drift or input error.
- `APPLIED`: profile written; target runtime still `NOT_VERIFIED` until verify.
- `UNCHANGED`: no profile change; not a cached verification result.
- `RESTORED` / `RECOVERED`: bytes restored, runtime `NOT_VERIFIED`.
- `UNINSTALLED`: managed profile removed; state remains for rollback.
- `PREVIEW` / `CLEANED`: cleanup preview or completed inactive-record removal.

`scope_warnings` are fixed notices, not blockers or plugin certifications. Explain
them with the normal change plan, without inventing a separate approval process.
Profile `verification_scope` is the selected workspace/profile, new-session-only;
command-rules evidence is native command decisions only. Plugin/source safety,
MCP/Web and resumed sessions remain unverified even when these checks PASS.

Exit 0 means the requested operation completed at its stated scope; exit 2 means
blocked, failed or incomplete. A report's explicit unverified subchecks remain
unverified even when the command itself succeeds.

### When inspection blocks setup

Read `configuration[].review_details` and `next_steps` before asking to apply.
Diagnostics name only a fixed catalogue of recognized setting groups and feature
names; they omit values, plugin identifiers, paths and arbitrary unknown names.
Unknown keys/features are counted. Recognition is not compatibility approval.
Users can inspect unnamed settings locally without pasting config into shared
logs. Do not delete settings, disable features or change homes to obtain READY.

A blocked plan has `applicable: false`, `candidate_status: REFERENCE_ONLY` and
`plan_id: null`. Its candidate is illustrative, not an installable plan. A READY
plan has `candidate_status: REQUIRES_APPROVAL`; it still needs human approval and
successful candidate probes. Existing plan IDs from earlier helper versions are
invalidated by the script fingerprint.

Compatibility work must distinguish display/speed preferences and bounded
extension metadata from plugin/tool policy, use version-matched evidence and
isolated tests, then rerun inspection.
The diagnostic vocabulary itself does not expand accepted settings. The separate
0.166.0 bounded user-preference adapter is described in
[compatibility.md](compatibility.md#01660-bounded-user-displayspeed-preferences).

## Probe boundaries

Candidate tests run in a temporary Codex home/workspace. `verify` uses the selected
home/profile and creates a temporary `.acp-probe-*` directory in the target
workspace. Both create an external temporary directory and a loopback TCP
listener. Test children print only fixed START/ALLOWED/DENIED markers. Before a
denial can count, the unsandboxed control must succeed; the network control also
runs after the sandbox test. No shell, model, HTTP request or live secret is used.

The native CLI may create its own helper/cache files under the selected Codex
home when invoked. Those are Codex-owned and are never removed by this manager.
The subprocess environment deliberately omits credentials, proxies and shell
startup variables; results are scoped to that controlled environment. The
network test checks loopback TCP denial, not every protocol or egress route.

Each child has a 15-second deadline and 128 KiB combined output limit. Config
inputs are regular, single-link files at most 1 MiB; inspected layers are capped
at 400 files and 8 MiB combined. Limits reject incomplete checks rather than
silently excluding inputs. No OS memory-isolation claim is made.

## Recovery

Profile verification additionally runs the synthetic credential catalogue checks.
This tests the policy without accessing real stores; it does not certify every
live credential path. Command-rules verification uses native execpolicy decisions
only, not a live agent or approval UI. Results distinguish these scopes.

`rollback`, `uninstall`, and `cleanup` use the same target arguments. Cleanup is
preview-only unless `--apply` is supplied. Rollback toggles the current and
previous generated texts (including original absence). Uninstall is idempotent.
Cleanup removes only this mode's inactive state record, losing its previous text;
it keeps the permanent lock, active records, pending journals and unknown files.

A journal is written before a profile change. If interrupted, normal apply stops.
`rollback` accepts only a target and state still matching either recorded side
of that transaction, then restores the before-state. Otherwise it preserves the
files and reports drift. Do not delete a journal or lock to force recovery.
The permanent lock inode is retained to avoid races between old/new lock files.

When rollback follows a Codex update, it can restore bytes without executing the
new binary. It does not downgrade Codex or certify that the old config works.
