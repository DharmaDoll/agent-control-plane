# Operations

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
  --workspace /absolute/repository \
  --mode development
```

Replace `inspect` with `plan` for the candidate. After reviewing its scope, use
`apply` with the same arguments plus `--plan-id <reported-plan-id>`. Then run
`verify` with the same arguments. `review` is the other supported mode.

`inspect` and `plan` leave the target unchanged. They parse bounded config files
and run version/help checks in a temporary synthetic home with a minimal
environment. They never load `auth.json` or enumerate session/log contents.

## Files and selection

The only managed profiles are:

- `<codex-home>/acp-review.config.toml`
- `<codex-home>/acp-development.config.toml`

State and a permanent advisory lock live in `<codex-home>/codex-hardening-state/`.
Records contain current/previous **generated** profile text, not copies of base
config or credentials. Profiles/records are mode 0600; state directory is 0700.
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

Exit 0 means the requested operation completed at its stated scope; exit 2 means
blocked, failed or incomplete. A report's explicit unverified subchecks remain
unverified even when the command itself succeeds.

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
