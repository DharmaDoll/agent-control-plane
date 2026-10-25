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
