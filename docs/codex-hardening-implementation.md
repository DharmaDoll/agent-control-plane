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

## Default protections (2026-10-29)

Accepted scope: deny common credential locations by default; provide explicit,
named opt-outs visible in plans; refuse sudo and request review for recursive
removal using native command rules. Preserve existing rule files, accepting only
a bounded literal prefix-rule subset after native validation. Unknown syntax
still blocks. No real-home deployment, credential reads or publication.

Implementation slices and acceptance:

1. Credential catalogue and deterministic profile generation, including AWS,
   Google Cloud, Azure, OCI, Kubernetes and common developer credential stores.
   Exceptions must change plan IDs; unknown exceptions fail closed.
2. Separate home-wide command-rules lifecycle, because native rules are not
   profile-scoped. Reuse atomic single-file recovery; show this wider scope.
3. Existing literal rules are parsed without evaluating Python/Starlark code;
   native execpolicy checks establish decisions. Preserve unknown/edited files.
4. Native 0.165.0 synthetic enforcement and lifecycle tests, complete regression,
   documentation and explicit limitations. Older binaries require fresh evidence
   before the new protections can be advertised as verified on those versions.

Command rules are not an OS syscall filter. Prefix matching cannot establish
every equivalent deletion or wrapper; no claim of universal deletion prevention
or tested approval UI is permitted. Credential checks use synthetic data only.

Implemented: 21 credential groups / 26 exact paths, named opt-out comments and
plan binding, explicit user-home targeting, separate home-wide command-rules
lifecycle, bounded literal-rule parsing and native decisions. Existing allows
are preserved and reported as a potential sandbox escape, not certified safe.
Native 0.165.0 default probes passed before adding the exact recipe. Older
versions remain identifiable but cannot apply the new protection set untested.

Boundary evidence: making the user home itself the writable workspace caused
a 0.165.0 bwrap missing-path mount failure. Inspection now explicitly blocks
workspaces containing the home rather than widening access. Distinct user/Codex
homes and a symlink to a synthetic credential pass the denial tests in a normal
project layout. Other aliases, missing paths and live credential stores remain
outside those claims. See the validation record for final execution evidence.

## Scene-first setup (2026-10-30)

Accepted scope: make the existing review/development templates the default setup
interface. Users choose a scene instead of manually authoring a profile. Keep
runtime permissions and the deterministic renderer unchanged; no additional
presets, auto-activation, deployment or batch transaction are introduced.

Implemented in SKILL.md, operations.md and the Japanese README: inspection,
scene selection, scoped plan approval, local generation, verification and explicit
new-session selection. Both profiles are optional independent installations.
Home-wide command rules remain separately approved; switching scenes does not
remove rules or reset exceptions. Generated absolute paths are not portable.

Acceptance review: first-time setup needs no existing profile; both scene choices
state their restrictions; switching and exception changes retain verification
and approval boundaries. Documentation reviewed against the existing renderer
and CLI mode choices. This is a workflow/documentation change, not completion of
the separate permission redesign or automatic installation detection roadmap.

## Quickstart blocker diagnostics (2026-10-31)

Real-home inspect/plan on native 0.165.0 stopped for feature flags and unknown
top-level configuration. Sanitized review identified fast_mode, notice, tui and
plugins, plus one uncatalogued key; 60 existing allow rules were reported.
No settings or credentials were changed and no profile was deployed.

Implemented: a fixed diagnostic vocabulary (not an acceptance allowlist), counts
for arbitrary keys/features, fixed next-step guidance, and reference-only blocked
candidates with no applicable plan ID. Tests cover non-disclosure of values and
private key/plugin names, preservation of config, malformed feature shape and
continued READY plan lifecycle. Existing policy restrictions remain unchanged.

Remaining compatibility work: classify exact nested preference settings using
version-matched evidence and native fixtures; separately assess plugin/tool
permissions and the uncatalogued key. Current official documentation describes
fast_mode as speed selection, but documentation alone does not validate the
installed runtime or an entire tui/notice/plugins table. Do not use blanket
top-level acceptance to make this home pass. Sources consulted:
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
and [configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic).

## Bounded user preferences (2026-11-01)

Implemented display-v1 with exact nested fields/types/limits and user-layer-only
scope. Tests cover preservation, boolean/int confusion, size limits, unknown
nested fields, plugin/source review and resumed-workspace review. The previously
unnamed real-home key was identified as marketplaces via official-schema name
matching; no source URLs, plugin names or config values were published.

During validation the native installation changed externally from 0.165.0 to
0.166.0. The initial version assertion failed as intended; no binary update was
performed here. Independent review/development Sandbox and credential fixtures
passed on 0.166.0 before adding its exact recipe. User preference lifecycle and
negative native parser checks then passed. New preference support is NOT enabled
on 0.165.0 without that unavailable binary's evidence.

Real-home inspection now recognizes all relevant groups and no longer blocks
fast_mode or the validated display settings. Remaining blockers are explicit:
plugin activation, marketplace source and session-selected resume workspace.
Resolving these requires a separate trust/scope decision, not wider display
allowlists. No live deployment, plugin execution, configuration change or Git
publication was authorized or performed. See evals/validation.md for test results.

## Accepted scope refinement (2026-11-03)

The user approved ordinary plan approval and recoverable, narrowly scoped
configuration changes rather than a separate plugin approval mechanism.
Plugin/marketplace presence alone should not block profile management. Preserve
those settings and report their execution surfaces as NOT_VERIFIED; do not
execute, install, update or certify plugins. Known permission conflicts, unknown
authority-affecting settings and failed/incomplete probes must still stop the
affected operation. Bind evidence to the tested workspace, configuration and
binary; a different resumed workspace cannot inherit it.

Implemented: bounded user-layer plugin enablement/marketplace metadata validation
in the 0.166.0 adapter, fixed scope warnings across inspect/plan/apply/verify,
and new-session/workspace evidence limits. Unknown nested authority fields,
invalid types/limits, project overrides and permission conflicts still block.
No additional plugin approval switch or execution mechanism was introduced.

Tests cover metadata preservation, stale-plan rejection, drift-safe rollback,
uninstall/restore, native parsing failures and local sandbox enforcement with
synthetic extension metadata. All 82 tests passed on native 0.166.0 under
host-approved execution. Real-home read-only inspection is READY with separate
unverified-surface warnings; no live profile was applied or verified. The
upstream cheatsheet comparison is now documented in limitations.md and linked
from the Japanese README: this manager implements selected controls, not the
entire upstream template. See evals/validation.md for reproducible evidence.
Recovery restores managed configuration, not prior external side effects.
No real-home apply, Git publication or automatic rollback over user edits is
authorized. Live plugin execution, resumption and approval UI remain NOT RUN.
