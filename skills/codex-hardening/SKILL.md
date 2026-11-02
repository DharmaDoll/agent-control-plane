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

Default protections have exact 0.165.0/0.166.0 recipes on Linux x86_64. Historical
0.163.0/0.164.0 recipes remain identifiable, but new apply/verify stops until
these protections are tested there. Unknown versions can be inspected, but
cannot be applied. Read [compatibility.md](references/compatibility.md)
when a version, command interface, config layer or policy model has changed.
Never turn an unrecognized setting into an assumed safe default.

## Plan and apply authorized changes

Start with scene selection, not a request to design a profile. Read
[operations.md](references/operations.md#choose-a-scene) for the two built-in
presets, first-time setup and later switching. Recommend `development` for code
changes and `review` for investigation. If the requested scene is already clear,
use it without asking again. Otherwise present both choices and their limits.
Users do not need to create a profile manually before using this skill.

Use `plan` to instantiate the selected preset and obtain a plan ID. Templates
are built into the manager; do not invent TOML or copy another machine's finished
profile. Both modes disable sandboxed command networking and
request human rather than automatic review for approval-requiring operations.
The permission profile does not grant writes to general temporary directories;
some tools need an explicitly reviewed alternative. Existing secrets/history/MCP
settings are not rewritten. Read [limitations.md](references/limitations.md).

Read [default-protections.md](references/default-protections.md) before setup or
exceptions. Propose credential-denying profiles and separate `command-rules`
(sudo forbidden, rm prompt, selected root/home removal prefixes forbidden).
Explain that rules affect the entire Codex home; obtain scope-specific approval.
Require explicit OS `--user-home`, distinct from `--codex-home`, without reading
credential contents. Keep protections enabled unless the human approves named
`--disable-protection` exceptions. Explain affected CLI use first; never opt out
or retry unsandboxed merely to make an operation succeed.

Apply only after the user accepts the target and changes. Use `apply --plan-id`
from the reviewed plan. The manager rechecks fingerprints, tests the candidate
in an isolated home, and creates/updates only its own named config profile and
management state. It does not activate a profile in existing sessions, rewrite
base config, or make the profile the global default. A stale plan requires a new
plan, not a force option.

Create only the selected preset by default. If the user requests both, plan,
approve, apply and verify each separately; report partial completion explicitly.
Choosing a preset is not approval to install the home-wide command rules. When
switching to an already installed preset, verify it for the intended workspace
and show a new-session invocation; do not regenerate it or silently drop existing
exceptions. If the requested exceptions are unknown, establish them before
planning or verification. Changing exceptions requires a fresh approved plan.

Existing managed policies, project configs/hooks, unsupported rule syntax,
permission settings or feature flags may require additional compatibility work.
Do not delete them, change trust levels, switch homes, or silently use another
policy model to make this helper pass. This initial implementation deliberately
stops where it cannot establish the necessary configuration boundaries.

For 0.164.0, five bounded project preference keys can be preserved without
blocking the local-command policy. Explain `configuration` classifications:
`COMPATIBLE` is narrow policy eligibility, `REVIEW_REQUIRED` is unverified,
and `CONFLICT` is an incompatible policy or invalid preference. Both latter
states block apply. Consult compatibility.md before interpreting the result;
none certifies model behavior, MCP, or confidentiality.
For 0.165.0, literal prefix rules can coexist after native validation. Review
`existing_rule_allow_count`/`rule_warning`: existing allows may bypass filesystem
protections. Preserve those files; syntax validation does not authorize grants.
The 0.166.0 recipe additionally preserves a bounded set of user display/speed
preferences. Consult compatibility.md for exact fields and limits; do not treat
an entire tui/features table as safe. Bounded plugin enablement/marketplace
metadata can coexist without a separate plugin approval. Unknown policy fields
and invalid metadata still block. Explain `scope_warnings` before ordinary plan
approval: plugin execution/sources are NOT_VERIFIED, and resumed workspaces cannot
inherit new-session evidence. Preserve existing configuration; never fetch or
execute a plugin as part of this compatibility check.

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
