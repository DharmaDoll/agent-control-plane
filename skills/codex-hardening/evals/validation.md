# Validation evidence

## Tested artifact and environment

2026-10-24 implementation working tree; Linux x86_64, Python 3.13.5 and native
Codex CLI 0.163.0. No existing Codex home, authentication, repository hook or
ModelForge deployment was changed. New configuration files used in tests were
confined to temporary homes/workspaces. No model/API call was used.

SHA-256 at the final runtime test run:

| Artifact | SHA-256 |
| --- | --- |
| `scripts/harden.py` | `f97b5e0a786bca5333e1d20f2d39a43bb06a66bb3825a4288ef9cf34486aa317` |
| `evals/test_harden.py` | `80b706a326d516178a5045751a447dcd3079c43c83e51ecc3503ef46eca3be7a` |
| `compatibility/recipes.json` | `42e6a7305a51f88ab1c063ddc6709b561e7894b82f0d0fea6376220d4af5246f` |
| Native Codex executable | `399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215` |

The executable was the already-installed npm distribution's native ELF, located
through its installed JavaScript launcher. This is local provenance/change
identification, not a new vendor-signature verification or redistribution.

## Automated results

```sh
CODEX_HARDENING_BINARY=/absolute/trusted/native/codex \
  python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v
```

- PASS: 36 tests, no skips, 19.792 seconds. Includes actual native CLI probes for
  both modes and real install/verify/uninstall/rollback/cleanup in temporary homes.
- PASS: existing controlled-github suite, 30 tests, 4.257 seconds.
- PASS for executed cases: existing secret-checks suite, 128 collected, 91 passed,
  **37 skipped**, 33.358 seconds. Docker, pinned-runner and other opt-in cases were
  not enabled; this is not a full Gitleaks/Docker certification. Its code was not
  changed by this task.
- PASS: skill-creator `quick_validate.py` on the new skill.
- PASS: Python AST/whitespace and local-link checks across 10 new/changed text
  files (33 local links), expanded Python secret scan, and `git diff --check`.
  Test-generated Python bytecode was moved to a temporary archive, not included
  in the deliverable; pre-existing `skills_plan/` drafts were preserved.

Unit/lifecycle tests mock native detection/probes where appropriate to isolate
state transitions; the separate opt-in real tests do not mock OS enforcement.
Without `CODEX_HARDENING_BINARY`, both real tests explicitly skip. Some negative
control tests also need local socket permission. Run the suite in a host-approved
context rather than claiming a restricted outer sandbox proved inner denial.

Coverage: intents, exact version support, CLI capabilities, fingerprints, bounded
output/time, environment filtering of the manager's subprocesses, unknown config,
opaque policy layers, redaction, malformed/oversized files, links, stale plans,
failed candidates, unmanaged collisions, idempotence, verify reruns, user edits,
concurrent writer locks, crash-before-write/crash-after-write recovery, recovery
drift, inactive cleanup and unsafe management-directory permissions.

## Failures found and corrected

- Test-first: both intent tests initially failed on an empty renderer, then
  passed after implementation. These were expected missing-behavior assertions.
- Outer-sandbox execution initially denied socket creation. Re-ran with explicit
  host approval; did not weaken the policy being tested.
- Actual 0.163.0 required `--permission-profile` for the chosen sandbox invocation.
  Replaced the initial legacy candidate with an explicitly tested permission
  profile recipe. Stable read/write/network intent remained unchanged.
- Actual `codex sandbox` rejected `--strict-config`. Removed that incompatible
  invocation, retained local parsing and real behavior checks. Startup failure
  consistently returned NOT_VERIFIED rather than a successful denial.
- An ignored-sandbox negative control demonstrably produces FAIL for outside
  writes and network; a startup-failure negative control produces NOT_VERIFIED.

## Not claimed

Agent-behavior evals, interactive approval UI, environment filtering of live
model-created commands, Web/MCP behavior, external egress protocols, log retention,
other Codex versions, other architectures/OSes and deployment into the user's
actual Codex home are NOT RUN. The live checks exercised the controlled native
sandbox interface, not a running interactive model session.

CodeGuard guidance informed fixed/redacted diagnostics, synthetic data,
structured subprocess arguments, execution/input limits, least-scope writes and
SHA-256 change detection. No cryptographic key, certificate, remote service,
credential migration or new authentication scheme was introduced.

## Review remediation evidence (2026-10-25)

Working tree based on `464ae7c878e2991745cc63d2fdd5af83a2969ea8`:
[Issue #9](https://github.com/DharmaDoll/agent-control-plane/issues/9) user/project
classification fix and a partial
[Issue #10](https://github.com/DharmaDoll/agent-control-plane/issues/10) expansion
of real-CLI metadata-protection tests. No permission profile, recipe or normal
`verify` probe was changed. User settings and authentication were not modified.

Final code artifacts:

| Artifact | SHA-256 |
| --- | --- |
| `scripts/harden.py` | `afadf0152f0143f729eba070c8e9bba745fe2a0a012dd19a98c3a8b253f7f8e5` |
| `evals/test_harden.py` | `85c26bc9f7e4da16cdb5078198e81fbabbbf839f7faea437ec3173f505b37c4b` |
| `compatibility/recipes.json` (unchanged) | `42e6a7305a51f88ab1c063ddc6709b561e7894b82f0d0fea6376220d4af5246f` |

### Test-first and regression results

- Baseline: 36 tests collected, 34 passed / 2 real-CLI tests skipped. The first
  restricted execution had two socket-creation errors; the host-approved rerun
  passed the executed cases. Neither error was treated as sandbox enforcement.
- Added `ConfigLayerTests` with real temporary files, collector and parser.
  Only native detection and reads outside the fixture/skill are mocked.
  Before the fix: 9 tests, 4 expected failures caused by the spurious project
  role. After the fix: all 9 passed (0.058 seconds).
- Intermediate #9 tree: 46 tests passed, no skips (33.154 seconds), including
  native 0.163.0 and real lifecycle tests in both sibling and normal-HOME layouts.
  This run predates the two metadata-protection tests, so it is not a full test
  run of the final test-file hash above.
- Final code, real-CLI subset: all 5 tests passed (30.806 seconds), including
  both-mode metadata protection and lifecycle checks. Native version assertion
  and recipe checks passed for 0.163.0. Its observed executable hash earlier in
  the task was `399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`;
  there was no post-run hash capture for this successful subset.
- Final full native run: **FAIL**, 48 tests collected, 5 assertion/subtest
  failures (6.669 seconds). The same executable location now reported 0.164.0;
  version matching failed and both lifecycle layouts returned
  `UNSUPPORTED_VERSION_OR_PLATFORM`. The subsequent executable hash was
  `b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306`.
  The task did not update Codex. This is runtime drift/unsupported-version
  evidence, not a reason to weaken the recipe or claim a full-suite PASS.
- Final CLI-independent run: 48 collected, 43 passed / 5 real-CLI tests skipped.
  Command: `python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v`,
  without `CODEX_HARDENING_BINARY`, in the host-approved socket-capable context.
- Skill structural validation and `git diff --check` passed. Other skills were
  unchanged; their regression suites were not rerun for this narrow change.

### New checks and remaining scope

The layer tests verify one read/user classification of the overlapping config,
custom homes, workspace equal to HOME, distinct ancestor/project configs,
permission conflicts, hook/rule deduplication, preservation of managed roles,
link refusal and changed plan IDs. Existing parsing and mutation controls remain
in place; arbitrary config compatibility is not newly granted.

Metadata tests create disposable `.git`, `.agents`, `.codex`, `.aws` directories
and a real Git separate-gitdir fixture. The resolved gitdir is deliberately
inside the writable workspace, so ordinary outside-workspace denial cannot mask
missing gitdir protection. Every tested target must be writable in an
unsandboxed positive control, then return the fixed DENIED protocol and remain
absent after the sandboxed attempt. Neither live user metadata nor credentials
are used. These are tests, not new installed enforcement mechanisms.

Issue #10 remains partial: representative Python/Go/Node development workflows,
combined-skill operations, linked worktrees, Docker, WSL2, approval UI and live
agent/MCP evaluations are NOT RUN. No 0.164.0 support is claimed. Re-running the
supported-version full suite requires a trusted 0.163.0 binary; evaluating a new
version follows the existing compatibility procedure, not automatic installation
or a broader version allowlist.

## Continued remediation and 0.164.0 evidence (2026-10-25)

This section supersedes the previous runtime blocker, not its historical results.
No Codex installation or real user configuration was changed. The installed
native 0.164.0 executable was tested separately before adding its exact recipe.
Its SHA-256 was
`b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306`;
real test classes check identity before and after execution.

Evidence: current official [permissions](https://learn.chatgpt.com/docs/permissions),
[configuration layering](https://learn.chatgpt.com/docs/config-file/config-advanced)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference),
native help markers, both-mode enforcement probes and lifecycle tests. A
version-matched source/schema diff was not available/reviewed; this is bounded
runtime evidence, not a claim of complete release compatibility. The old
0.163.0 binary was unavailable for a fresh rerun (NOT RUN).

### Reproduction and results

Use a trusted installed native executable, Python 3.11+, and a host that permits
the local sandbox/loopback tests. No model or remote service calls are required.

```sh
CODEX_HARDENING_BINARY=/absolute/path/to/native/codex \
CODEX_HARDENING_EXPECTED_VERSION=0.164.0 \
CODEX_HARDENING_WORKFLOWS=1 \
python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v
```

- Final run: **60 tests passed, no skips, 63.906 seconds**. Python 3.13.5,
  Node.js 18.12.1, Go 1.24.4 and Git 2.47.2; existing tools only.
- Exact-version regression initially failed for unsupported 0.164.0, then
  passed after separate both-mode probes and recipe addition.
- Preference classification: six tests initially produced 19 failing assertions;
  after implementation all 15 layer/preference tests passed. The real trusted
  project test verifies native parsing, unchanged preferences, and refusal of
  a later permission override before probing.
- Python and Node builtin test fixtures passed in the sandbox (0.159 / 0.360s).
- Go default cache placement was denied (exit 1, 0.073s); explicitly placing
  cache and temporary directories inside the fixture workspace passed
  (exit 0, 7.692s). Offline settings disable module downloads/toolchain updates.
  This is a deliberate test configuration, not automatic permission escalation.
- Git positive controls add, commit and push to a disposable local bare repo
  succeeded outside the inner sandbox. Subsequent sandboxed add and commit were
  denied (exit 128); HEAD/index were unchanged. No real remote was contacted.
- Offline workflows are separately opt-in. Missing tools cause explicit skips,
  never installation. Output contains only fixed labels, exit codes and timing.

Tested artifact SHA-256:

| File | SHA-256 |
| --- | --- |
| `scripts/harden.py` | `6c5b4cccf9beaf228853518aa0e7c7021bc3d02f7ca4e5c83388fa794af3d429` |
| `evals/test_harden.py` | `62728685cd34dc54f792b22bebc544528fe393c45fa5f2c31f6e83682c291717` |
| `evals/test_workflows.py` | `d4d713b8643a538e95916da01fbbaf8abf2b7c1571c77da39a57b8212becbc90` |
| `compatibility/recipes.json` | `c802a9a200c009c5ec7620da64e4f311ec3d35bc584edf377437f50c8a46e35c` |

Remaining NOT RUN: combined-skill handoffs, linked worktrees, dependency
downloads, Docker, WSL2, approval UI, live agent/MCP behavior and other skills'
regression suites for this change. Runtime `verify` still measures its original
three probes; additional metadata/workflow checks are isolated evaluation tests.
No profile permissions were widened and no production deployment was performed.

## Default protections (2026-10-29)

Tested native Codex: **0.165.0**, SHA-256
`c06a67fd8ac76508dc78bd99ce20c9f317b8d568beda59485f3f4134df9962d5`.
The installation changed outside this task; no binary was installed/upgraded.
Both original sandbox modes and the synthetic credential checks passed before
adding the exact 0.165.0 recipe. Current official permissions/rules documentation
and native help/behavior were checked; no version-matched source/schema audit
or live agent session was performed.

### Final run

```sh
CODEX_HARDENING_BINARY=/absolute/path/to/native/codex \
CODEX_HARDENING_EXPECTED_VERSION=0.165.0 \
CODEX_HARDENING_WORKFLOWS=1 \
python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v
```

**71 passed, no skips, 78.025 seconds**, in a host-approved execution context.
This includes the existing offline Python/Node/Go/Git workflows. Real-CLI test
classes compare executable identity before/after. The protection subset also
passed independently: 11 tests, 34.633 seconds. No real credentials or remote
services were used. Native execpolicy checks receive sudo/rm only as data;
they do not execute those commands.

Tested artifact SHA-256:

| File | SHA-256 |
| --- | --- |
| `scripts/harden.py` | `38eb76da82e8689b1b289f6c61af77fa699ef6133cc1ca57ba44739be2a7de0b` |
| `evals/test_harden.py` | `cd86032a7ce4b84b16be7ccf69cfd05a437cda2d817ea8928868599ddd2a80c2` |
| `evals/test_protections.py` | `7816a00610c56d2a9ef29f12defc98db8897843ab12d159c548275b4b8a4ce2a` |
| `compatibility/recipes.json` | `d79eaa5724a078a608149f6e1c94bca97b60f43a675f896cb847a80f796db1fd` |

Coverage includes default read denial for all 26 synthetic paths in 21 groups,
AWS-only opt-out with other groups still denied, both modes, explicit user home
different from Codex home, symlink access to a protected fixture, exception plan
binding, no credential reads by inspection, unknown exception refusal, bounded
non-executing rule parsing, invalid native inline tests, stricter decision
precedence over existing allows, command-rules apply/verify/opt-out/rollback/
uninstall/cleanup, original-file preservation, collisions, edited targets and
interruption recovery. Existing layer/lifecycle/drift regressions remain covered.

### Failures that informed the implementation

- Test-first default SSH denial failed as expected before implementation.
- An intermediate unprivileged run exposed two socket-permission errors, plus
  test-fixture signature/recipe updates and a real path-redaction regression.
  Plans now show symbolic homes while binding actual bytes with SHA-256;
  redaction assertions were preserved, not weakened.
- An intermediate 68-test native run stopped on
  `ENVIRONMENT_CHANGED_DURING_VERIFY` while the manager source was being edited.
  This is expected drift protection, not permission to bypass verification.
- A 71-test run failed when the user home was also the writable workspace:
  native bwrap could not mount a missing credential-path parent. Startup failure
  was not counted as denial. Inspection now blocks that layout; regression tests
  assert this and normal project layouts separately. No deny was removed.

### Remaining boundaries

0.163.0/0.164.0 binaries were unavailable: their new protection behavior is
**NOT RUN**, so apply/verify blocks rather than reusing historical PASS results.
Approval UI, startup loading in a model session, MCP/Web, real credential stores,
arbitrary hardlinks/mounts/missing paths, custom credential locations, Windows,
macOS and WSL-specific enforcement remain NOT RUN. Existing allow rules can
authorize sandbox escapes and are reported for human review, not certified safe.
No deployment, authentication changes, commit or push were performed.

## Quickstart diagnostics regression (2026-10-31)

Changed artifacts (SHA-256):

- scripts/harden.py: `a704a920b3559835c4cb98ceef7e0e392706f827fa03433a393bc2dfcf976a7d`
- evals/test_harden.py: `c15128b42b7aa40104fb64972808110af5d9ac192b36456149c35369ce73fabb`

Three new tests cover reference-only blocked plans, READY plan eligibility and
malformed feature diagnostic redaction. The plan-focused test-first run failed
on the missing `applicable` contract; all three pass after implementation.
The sandboxed regression run had two socket PermissionErrors (environmental),
58 passes and 14 skips. Host-approved rerun: 60 passes, 14 opt-in skips.

Full host-approved run with CODEX_HARDENING_BINARY pointing to native 0.165.0,
CODEX_HARDENING_EXPECTED_VERSION=0.165.0, CODEX_HARDENING_WORKFLOWS=1:
`python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v`
completed **74 tests, all PASS, no skips, 99.051 seconds**. Synthetic fixtures
only; native profile, rule, recovery and offline development checks included.

Real-home plan rerun remains BLOCKED (exit 2), now with safe setting group names,
next steps, applicable=false, candidate_status=REFERENCE_ONLY and plan_id=null.
No real config mutation or deployment occurred. Acceptance policy is unchanged;
this result does not certify compatibility of fast_mode, notice, tui or plugins.
Live interactive activation and approval UI remain NOT RUN.

## Bounded user preferences and runtime drift (2026-11-01)

The first new test-first run failed because configuration_issues had no user
preference adapter argument. Four unit tests then passed after implementation.
The initial native test expected 0.165.0 and failed on observed **0.166.0**. The
installation changed externally; no upgrade/downgrade was executed by this task.
The old binary was unavailable, so display-v1 was not enabled for 0.165.0.

Native 0.166.0 executable SHA-256:
`b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`.
Before adding its exact recipe, direct review/development Sandbox probes and
synthetic credential-denial probes all passed. Five focused preference tests
then passed, including native lifecycle preservation and negative parser controls.

Full host-approved regression command used CODEX_HARDENING_BINARY set to that
native executable, CODEX_HARDENING_EXPECTED_VERSION=0.166.0 and
CODEX_HARDENING_WORKFLOWS=1 with:
`python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v`.
Result: **79 tests PASS, no skips, 102.419 seconds**. Skill quick validation and
git diff --check also passed. Tested artifacts:

- scripts/harden.py: `0215087b86961ebee2f8b8798481429896b7196491e53acf8b97f194b3d1fb48`
- evals/test_user_preferences.py: `9385083d92bcaf97397b6a892ee06d2803c26b6c6fac5e343617e6d159659b61`
- compatibility/recipes.json: `7dde96cf813965aebb15b2a60e23bc95df9659c1ba50c554dcb71947e926a846`

Real-home inspect remained BLOCKED (exit 2), now specifically for plugin
configuration, marketplace configuration and session-selected resume workspace.
No unknown top-level keys remained in the sanitized diagnostic vocabulary;
fast_mode and supported display settings were no longer blockers. No live config
was changed. Plugin names, source URLs, UI map entries and values were not exposed.

Current official schema/reference were consulted, not version-pinned source.
The native checks establish configuration parsing and local-command policy only;
TUI display semantics, live resumption, plugin activation/refresh, external MCP,
approval UI and actual deployment remain NOT RUN. Existing 0.165.0 historical
protection evidence is unchanged, not a new rerun or display-v1 certification.
## Scoped extension coexistence — 2026-11-03

- Added tests first: bounded metadata acceptance/lifecycle failed on the three
  presence-only blockers, and malformed metadata lacked the expected conflict
  reason. This was an intended requirement failure, not a runner/import failure.
- Implemented type/size validation, preserved existing bytes, and propagated
  fixed scope warnings without printing names, source URLs or values. Test data
  is synthetic; no real credential or certificate was read or embedded. Existing
  SHA-256 plan fingerprints and no-shell execution boundaries were retained.
- The initial sandboxed full run failed (18 failures, 11 errors) because the
  outer execution sandbox denied loopback/nested sandbox operations. It was not
  counted as evidence of successful policy enforcement. No assertions or policy
  settings were weakened. The same suite was rerun with host execution approval.
- Full suite: **82 tests PASS, no skips**, 97.896 seconds, native Codex 0.166.0,
  Python 3.13.5, Linux x86_64. Command:

  ```sh
  CODEX_HARDENING_BINARY=/absolute/native/codex \
  CODEX_HARDENING_EXPECTED_VERSION=0.166.0 CODEX_HARDENING_WORKFLOWS=1 \
  /usr/bin/python3.13 -B -m unittest discover -s skills/codex-hardening/evals -v
  ```

- Native synthetic-home test exercised metadata plus session-resume preference,
  plan/apply/verify, uninstall/restore/verify and base-config byte preservation.
  Invalid plugin Boolean and marketplace enum were rejected by the native parser.
  No installed plugin fixture, model, source fetch or external service was used;
  this does not prove containment of an actual plugin or resumed session.
- Unit lifecycle checks reject a stale plan after metadata changes and preserve
  a user-edited target on rollback refusal. Existing regression tests cover
  interrupted transactions, failed candidate probes, conflicts and drift.
- Real-home `inspect` only: READY, no issues, both layers COMPATIBLE; runtime and
  other surfaces NOT_VERIFIED. Three scope warnings identify plugin/marketplace
  uncertainty and resumed-workspace revalidation. Existing 60 allow rules still
  trigger the outside-filesystem-protection warning. No live apply/verify.
- Skill validator and `git diff --check`: PASS. Other CLI versions were NOT RUN
  for the new metadata behavior; their recipe eligibility was not broadened.
- Tested SHA-256 values:
  - native binary: `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8`
  - `scripts/harden.py`: `232500bb475a16bf5f3a7f6ff430d84a75fb0406440fe4890173b041e09ee33b`
  - `evals/test_user_preferences.py`: `47cff14b1ffcfffbdde8cc62dc84ccf2a3864ed7a7c7c2e95883fac5b700a520`
