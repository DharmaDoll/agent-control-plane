# Codex hardening implementation

## Accepted scope

Add a standalone `skills/codex-hardening` skill for Linux/WSL2 and Python 3.11+
(stdlib `tomllib`). No packages, Codex upgrades, authentication changes, active
user configuration changes, commits, or deployment are authorized by this work.
Keep unknown versions inspectable but do not apply unverified recipes.

Separate stable review/development intent, version-specific compatibility data,
and local evidence. Start with Codex 0.163.0; support is contingent on real probes,
not merely a version match. Manage two explicitly selected config profiles, not
the base configuration. Preserve unrelated settings and user-edited files.

## Slices and acceptance

1. Compatibility and read-only inspection: exact versions, native executable
   identity, bounded parsing, redacted diagnostics, configuration conflicts.
2. Plans and probes: reproducible plan fingerprint; positive controls for sandbox
   startup, writable paths, and network reachability; distinguish denial from
   infrastructure failure. No model or remote service calls.
3. Lifecycle: explicit apply, verify, rollback, uninstall, cleanup; atomic profile
   writes, a persistent lock, interruption journal and drift checks.
4. Distribution: concise skill, operational/compatibility/limitations references,
   Japanese README entry, isolated automated tests and honest evidence.

## Test strategy

Use stdlib unittest with isolated homes/workspaces. Cover unknown versions,
missing CLI capabilities, mixed policy modes, project/system overrides, malformed
and secret-bearing inputs, changed plans, profile collisions, links, interrupted
transactions, idempotence, recovery and cleanup. Run separate real CLI probes
with the installed native binary. Never interpret a mock as OS enforcement.

## Progress

- Planning: accepted; Python 3.13.5 is already available at `/usr/bin/python3.13`.
- Implemented all four slices; see the standalone skill's
  [validation record](../skills/codex-hardening/evals/validation.md) for commands,
  artifact hashes, actual results and unverified surfaces.
- 36 new tests passed including native CLI/lifecycle tests. Existing
  controlled-github: 30 passed. Existing secret-checks: 91 passed / 37 skipped.
- No live configuration was changed and no Git publication was performed.

## Evidence-driven implementation choices

- 0.163.0 requires explicit permission-profile selection for the sandbox test
  interface and rejects `--strict-config` for that command. Use the tested
  permission-profile recipe rather than legacy sandbox examples.
- Initial automatic management refuses opaque project/managed/hook/rule layers,
  existing permission models, feature flags and unreviewed keys. These remain
  intact; broader configuration support needs additional adapters and tests.
- Require the actual native ELF instead of fingerprinting an npm launcher that
  can remain unchanged while its underlying executable is replaced.
- Probe results are returned with a fingerprint and never cached as authorization.
  Version/config changes need a new plan and fresh probes; there is no automatic
  updater, startup wrapper or continuously running monitor.

## Previous review remediation handoff (2026-10-25)

The canonical staged plan and acceptance criteria are tracked in
[roadmap #15](https://github.com/DharmaDoll/agent-control-plane/issues/15).
This section is a local implementation handoff, not a second roadmap.

- [#9](https://github.com/DharmaDoll/agent-control-plane/issues/9): implemented
  in the working tree. The user config is no longer reclassified as project
  config in normal HOME layouts. Regression coverage uses the real collector
  and parser, including distinct project files, custom homes, conflicts,
  hooks/rules, aliases and plan invalidation. An additional real-CLI lifecycle
  case covers the previously missing normal-HOME layout.
- [#10](https://github.com/DharmaDoll/agent-control-plane/issues/10): partial.
  Added opt-in real-CLI tests for `.git`, `.agents`, `.codex`, `.aws` and a
  `.git` pointer to a separate gitdir located inside the writable workspace.
  Positive controls must write successfully before sandbox denial counts;
  tests also check the denied write left no file. These are disposable test
  fixtures, not additional probes against live user metadata during `verify`.
- Next: complete #10's representative development/workflow evidence and #11's
  version-specific configuration classification before selecting #12's profile
  changes. Go/Node workflows, combined skill handoffs, linked worktrees,
  Docker, WSL2, approval UI and live MCP/agent behavior have not been evaluated
  by this change. #11–#14 are not implemented.

Runtime handoff: the installed native binary changed from 0.163.0 to 0.164.0
during validation, without an update performed by this task. Earlier 0.163.0
lifecycle/protected-path checks passed; the final full run correctly rejected
the unsupported version. Do not describe the final run as passing or expand
the recipe merely to restore green tests. Resume runtime work with an explicitly
supplied trusted 0.163.0 binary or a separately evidenced 0.164.0 compatibility
change; do not downgrade or install a binary implicitly.

Profile permissions, supported versions, runtime probe behavior and existing
user configurations are unchanged. No credentials/certificates were introduced
or read; fixtures use synthetic values and existing SHA-256 plan detection.
No deployment, commit/push or Issue closure has been performed. See the skill's
[validation record](../skills/codex-hardening/evals/validation.md) for evidence
tied to the working-tree artifacts.

## Continued implementation (2026-10-25)

- The runtime drift blocker above is resolved by separately testing native
  0.164.0 and adding an exact-version recipe, not by changing the installation.
  Both modes retain the same permissions. Historical 0.163.0 evidence remains;
  its binary is unavailable for a current rerun.
- #11 now has a bounded first implementation: five project preference keys,
  typed validation, redacted per-layer classification and stale-plan checks.
  Real trusted-project tests verify preservation and refusal of permission
  overrides before probing. This is not general configuration resolution.
- #10 adds opt-in offline Python/Node/Go and local Git workflow fixtures.
  General temp/cache restrictions and Git metadata write denial are measured,
  not silently relaxed. Combined-skill handoffs, linked worktrees, Docker,
  WSL2, approval UI and live agent/MCP remain outstanding.
- #12 profile redesign, #13 detection UX and #14 release monitoring are still
  pending. No user configuration, installation, credentials or real repository
  deployment was changed; no commit, push or Issue closure was performed.
