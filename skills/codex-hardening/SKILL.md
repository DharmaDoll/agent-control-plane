---
name: codex-hardening
description: Inspect Codex CLI hardening and manage explicitly selected, version-tested review/development profiles with local sandbox probes and recovery. Use for hardening setup, configuration review, or revalidation after a Codex update; not ordinary coding or automatic upgrades.
---

# Codex hardening

Manage a small, testable local-command policy, not a universal security guarantee.
Requires Linux x86_64 (WSL2 is a candidate, not separately certified), Python 3.11+
with stdlib `tomllib`, and a trusted native Codex executable. No extra packages,
model calls, credential reads, downloads, or daemon installation are needed.

## Inspect first

1. Establish the requested operation, absolute workspace, actual Codex home and
   trusted native executable. Never substitute a different home to bypass an
   inspection failure. For an npm installation, locate its native executable
   through the installed launcher/package layout; do not execute an arbitrary
   downloaded binary. The helper rejects wrappers and symlink path components.
2. Run `inspect` with the bundled [manager](scripts/harden.py). See
   [operations.md](references/operations.md) for exact arguments and side effects.
   An inspection request does not authorize apply, verification writes, cleanup,
   auth changes or Codex upgrades.
3. Explain readiness, conflicts and observations without printing config bodies,
   rule files, process errors, environment dumps, credential values or MCP URLs.
   `READY` means this narrow recipe can be evaluated, not that the environment is
   secure. Other surfaces remain `NOT_VERIFIED`.

The current recipe supports exactly 0.163.0 on Linux x86_64. Unknown versions can
be inspected, but cannot be applied. Read [compatibility.md](references/compatibility.md)
when a version, command interface, config layer or policy model has changed.
Never turn an unrecognized setting into an assumed safe default.

## Plan and apply authorized changes

Use `plan` to generate a candidate and plan ID. Offer `review` (read-only) or
`development` (workspace writes); both disable sandboxed command networking and
request human rather than automatic review for approval-requiring operations.
The permission profile does not grant writes to general temporary directories;
some tools need an explicitly reviewed alternative. Existing secrets/history/MCP
settings are not rewritten. Read [limitations.md](references/limitations.md).

Apply only after the user accepts the target and changes. Use `apply --plan-id`
from the reviewed plan. The manager rechecks fingerprints, tests the candidate
in an isolated home, and creates/updates only its own named config profile and
management state. It does not activate a profile in existing sessions, rewrite
base config, or make the profile the global default. A stale plan requires a new
plan, not a force option.

Existing managed policies, project configs/hooks/rules, user rule files,
permission settings or feature flags may require additional compatibility work.
Do not delete them, change trust levels, switch homes, or silently use another
policy model to make this helper pass. This initial implementation deliberately
stops where it cannot establish the necessary configuration boundaries.

## Verify and report

Run `verify` after apply, and after changing the executable, configuration,
workspace or skill. It always re-runs probes; no cached PASS authorizes work.
Verification creates temporary synthetic files inside the workspace and outside
it, and a loopback listener; it does not call a model or an external service.
Ask for host execution permission when required; never weaken the target policy
to make a sandbox probe start.

Report configuration readiness separately from local-command probe results.
Human approval UI, environment filtering in model-created commands, Web, MCP,
logs and actual interactive-session activation require separate verification.
The CLI sandbox test is not proof about those surfaces. Show the expected new
session invocation; do not start an agent session automatically.

## Recovery and cleanup

Use `rollback` for the previous managed profile or an interrupted transaction,
`uninstall` to remove the managed profile, and `cleanup` to preview the inactive
record eligible for deletion. `cleanup --apply` loses that record's rollback
copy; require cleanup authority. User-edited, unknown, active and pending files
are retained. No credentials, session history or Codex installation is removed.

Restoring bytes after a version change does not establish compatibility; report
`NOT_VERIFIED` and revalidate. A previous profile can be restored after uninstall
until its record is cleaned. Git publication and real-environment deployment are
separate authorizations.

Automated evidence is in [validation.md](evals/validation.md). No process here
prevents an operator from launching Codex with different flags or bypassing this
skill. Keep OS permissions and credential/service boundaries outside the agent.
