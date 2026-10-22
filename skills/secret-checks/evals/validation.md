# Validation record

## Environment and provenance

Verification completed over 2026-10-19/20 (JST), on the implementation working tree
based on agent-control-plane `ddd13cd`.
Linux x86_64 / WSL2, Git 2.47.2, Python 3.10.4. Source implementations migrated
from product-security-guidance `2b5e81df0eee973d4cc4fc493fe09d93d207ea0b`.
Original Python baseline: 8 tests passed before migration.

Pinned Gitleaks: official Linux x64 8.30.1. Archive and binary SHA-256 matched
the values recorded in [gitleaks.md](../references/gitleaks.md). The preinstalled
local Gitleaks binary did not match and was not used as validated evidence.

## Automated tests

```sh
SECRET_CHECKS_GITLEAKS=/path/to/verified/gitleaks python3 -B -m unittest discover -s skills/secret-checks/evals -p 'test_*.py' -v
python3 -B -m unittest discover -s skills/controlled-github/evals -p 'test_*.py' -q
```

Git tests use temporary local worktrees/bare remotes and runtime-assembled,
non-issued canaries. Docker-specific tests additionally use the local daemon as
recorded below. No real credential, live GitHub push or target-checkout commit
is used.

| Suite / check | Observed evidence | Result |
| --- | --- | --- |
| Python scanner (`test_scan_sensitive.py`) | 14 tests, including original 8 scenarios and added redaction/unsupported-input regressions | PASS |
| Lifecycle manager (`test_manage_hooks.py`) | 16 tests, including real pinned Gitleaks installation/verification and cleanup; final rerun passed | PASS |
| Gitleaks adapter (`test_gitleaks_gate.py`) | 23 tests with verified 8.30.1 binary; no skips | PASS |
| Existing controlled-github regression | 30 tests | PASS |
| Skill structure | `skill-creator/scripts/quick_validate.py skills/secret-checks` | PASS |
| Docs / syntax / whitespace | 34 local links across 21 Markdown files; Python AST and shell parsing; 18 changed/new text files checked | PASS |
| Guidance reference migration | `python3 -B scripts/check_docs.py`: 3,421 local links, 54 control IDs, zero errors | PASS |

The initial full secret-checks run passed 52 tests before the final inspection
scenario was added. Final evidence is maintained per affected suite; the Gitleaks
adapter's executable code was unchanged after its 23-test run. Do not mistake a
test count for independent assurance or a production deployment.

Coverage includes inherited scanner behavior, merge-only findings, staged versus
worktree differences, unsupported formats, metadata/output redaction, actual Git
hook invocation, versioned installation/update/rollback/uninstall, configuration
drift, failed preparation, cleanup preview/protection, symlinks and modified or
unknown files. Gitleaks additionally covers tags, receiver reference behavior,
report/exit disagreement, timeouts and fixed-rule isolation.

If `SECRET_CHECKS_GITLEAKS` is absent, tests that require the real pinned binary
explicitly skip. Skipped tests do not prove the Gitleaks engine passed. Fault
injection tests and real-scanner tests are different evidence.

## Combined engine addition (2026-10-20)

The combined dispatcher and lifecycle changes were tested on the working tree
based on `2889ee1`, using the same digest-verified Gitleaks binary above.

- Full regression run: 62 tests passed with no skips (Python 14, Gitleaks 23,
  dispatcher 6, lifecycle 19 at collection time). After strengthening the
  combined probe and adding its regression case, the final lifecycle suite below
  passed separately; do not interpret this as a single 63-test run.
- Dispatcher: 6 tests passed, including all 16 combinations of successful,
  finding, error, and unexpected child exits; order, stdin replay, argument
  boundaries, suppressed diagnostics, missing child, and timeout handling.
- Lifecycle manager: 20 tests passed with the real pinned binary, no skips.
  Added coverage includes Python-to-combined update, Gitleaks binary reuse,
  rollback, verification, cleanup, missing child refusal, and rejection when
  Python passes but Gitleaks cannot scan an oversized input. A fault-injected
  always-successful child was rejected by the installation probe without
  changing the active bundle.
- Skill structure, local Markdown links, Python syntax, and whitespace passed.

Tests use inert fixtures, not issued credentials. Child diagnostics are discarded
to prevent accidental disclosure through errors. Existing SHA-256 binary pinning
is retained; no certificate handling, authentication, or network acquisition was
introduced. These checks follow the skill-creator validation workflow and
CodeGuard guidance on secret-free fixtures, structured subprocess arguments,
bounded execution, and non-sensitive output.

No target repository installation was migrated by this change.

## Docker runtime addition (2026-10-20)

Verified on local Linux x86_64 Docker using the same pinned Gitleaks binary.
The opt-in command is:

```sh
SECRET_CHECKS_DOCKER=1 SECRET_CHECKS_GITLEAKS=/path/to/verified/gitleaks python3 -B -m unittest discover -s skills/secret-checks/evals -p 'test_*.py' -v
```

Without `SECRET_CHECKS_DOCKER=1`, the real Docker lifecycle is skipped even if
the verified binary is available. Such a run does not validate Docker execution.

The first Docker suite passed 8 tests (7 command-contract cases and one real
combined lifecycle). The expanded real lifecycle also passed: default Docker
selection, runtime-preserving update, native update and Docker rollback,
configuration/integrity probes, missing-manifest refusal, and image-retaining
bundle cleanup. Final command-contract tests passed all 8 cases after adding
malformed/missing/oversized manifest refusal.

The full regression collected 71 tests: 69 passed, and two existing fault-injection
tests errored because their manually constructed Scanner fixture lacked the new
runtime field (eight error entries including subtests). The fixture was corrected
to initialize native mode; both affected tests then passed in a focused rerun.
The additional manifest-contract test also passed in the final 8-case contract
run. There was no single all-green 72-test run; final evidence is per affected
case/suite. Real Gitleaks cases (21), manager cases (20), Python cases (14), and
combined dispatcher cases (6) passed in the full run.

The real probe exercises safe commit/push, staged and message findings, incomplete
input, and removed secrets retained in outgoing history. Contract fault injection
covers attach timeout, OOM, unexpected exits, failed container cleanup, unknown
create results, fixed build inputs, and non-sensitive error handling. These are
separate forms of evidence; a mocked timeout is not a live-daemon outage test.

No live target repository was migrated. Temporary labeled scan containers were
absent after the Docker lifecycle completed. A 22 MB test image remains in the
local daemon, consistent with the shared-image retention policy:
`sha256:c1ad3ad8e126385ed891d5ceaa6a3ef1ebc5dbb5f0f2ea199488b4bd7fa75e30`.
No global image/cache pruning was performed. The image is locally built from
verified binary bytes, not an upstream signed container release.

The skill-creator workflow keeps deployment decisions in the skill and detailed
procedures in references. CodeGuard guidance informed fixed image selection,
non-root/read-only execution, disabled networking, bounded resources, no host
mounts, exact container cleanup, and suppressed child diagnostics. No new
credentials, certificates, or authentication configuration were introduced.

## Issue #7: batch runner (2026-10-21)

Implementation working tree based on `638efd9154792017cc78863ca00fdafef4219632`.
Linux x86_64 / WSL2, Python 3.10.4, Git 2.47.2, Docker 26.1.4.
Final runner SHA-256:
`22f8bf7fa0fc37e1bbbabea9ebb294b14ceefd73688cb1f5243dde5a4b57de79`.
Built with Go 1.26.8, fixed Gitleaks 8.30.1, `gore2regex`, and the flags in
[runner.md](../references/runner.md). A second build in an independent temporary
build/cache directory produced the same digest. The offline helper refused to
overwrite an existing output; its digest remained unchanged.

### Automated evidence

```sh
SECRET_CHECKS_RUNNER=/path/to/verified/gitleaks-runner \
SECRET_CHECKS_GITLEAKS=/path/to/verified/gitleaks \
SECRET_CHECKS_DOCKER=1 SECRET_CHECKS_LEGACY=1 \
python3 -B -m unittest discover -s skills/secret-checks/evals -p 'test_*.py' -v
```

The final runtime passed **86 tests with no skips**, in 231.901 seconds:
batch adapter 7, dispatcher 6, Docker 9 (including live lifecycle), Git/Gitleaks
23, runner parity/protocol 4, historical migration 1, manager 22, Python scanner 14.
Historical migration reads the immutable revision above from the local Git object
database; its opt-in flag requires that revision and the official CLI to exist.
It validates refused migration without a runner, explicit update, old-bundle
rollback/verification, return to the new bundle, uninstall and cleanup.

Go's three runner tests passed with
`go test -mod=readonly -tags=gore2regex -count=1 ./...` using the pinned toolchain.
The existing controlled-github suite passed all 30 tests. Skill structure,
Python syntax and relative documentation links passed. No production hook,
authentication, GitHub Issue/PR, commit, push or merge was changed.

Tests compare the official CLI's per-input rule IDs with the batch runner,
including private-key, GitHub PAT and AWS-shaped inert inputs, ignored allow
comments, UTF-8, MIME-like text, empty inputs and large/chunk-boundary cases.
Runtime-assembled canaries are never issued credentials. A new boundary test
exposed an intermediate implementation's short header-only read: a multiline
canary near 25 KB was missed. A contiguous per-input reader fixed this; the
failure and its correction were observed before final validation. After the full
run, the isolation fixture was strengthened to use a token whose joined halves
are demonstrably detected; the affected Go and four runner tests were rerun.

The 500-input runner checks detect canaries at positions 0, 250 and 499 without
disclosing values. Fault injection verifies exactly one batch invocation, strict
completion/count/byte validation, malformed reports, deadlines, Docker failure
and exact-ID cleanup. These are not live OOM/daemon-outage simulations. Input
truncation, unsupported text and size violations also exercise the real runner.

### Performance

Commands use `evals/benchmark_gitleaks.py --runner /path/to/verified/gitleaks-runner
--runtime native|docker`, and `--runtime docker --engine combined --counts 236 500`.
Each case uses a new isolated repository and unique benign blobs. Measurements
cover the actual pre-commit hook including Git enumeration and, where applicable,
Docker creation/removal; image preparation and fixture setup are outside timing.

| Files | Content bytes | Native / Gitleaks | Docker / Gitleaks | Docker / combined |
| --- | --- | --- | --- | --- |
| 10 | 360 | 1.237 s | 1.153 s | NOT RUN |
| 150 | 5,590 | 3.666 s | 1.897 s | NOT RUN |
| 236 | 8,858 | 4.857 s | 2.329 s | 2.974 s |
| 500 | 18,890 | 6.552 s | 3.527 s | 4.926 s |

All measured runs returned exit 0 within the unchanged 120-second budget.
Native launches one detector process; Docker creates one scanner container per
hook, independently of input count (separately asserted by command-contract tests).
The full combined Git lifecycle additionally exercises real commit/push commands.

The pre-change measurements in [Issue #7](https://github.com/DharmaDoll/agent-control-plane/issues/7)
recorded 10-file runs at 18.67 s native / 25.33 s Docker, and 150-file runs at
120.06 s / 120.19 s with exit 2. Those fixtures contained 330 / 5,140 bytes and
are not byte-identical to this benchmark. The separately reported combined/Docker
236-entry timeout is adopter evidence, not a reproduction in that environment.
These are single local runs, not latency SLAs, a native-vs-Docker ranking, or
evidence for arbitrarily large repositories.

### Retained resources and limits

No labeled scan containers remained after the final tests. Two 15.3 MB test
images remain under the existing shared-image retention policy:
`sha256:aa8761b4329694ed59c478f15f57a1506480f23c1457fd23e808203c13a42812` and
`sha256:b3ae88bbc63e3484178521a0e526d39ee5057beb2cd3bd058301d90c3f717038`.
The pre-existing 22 MB CLI image also remains; no image/cache pruning was used.
Build artifacts and Go cache are caller-owned; no binary is added to the skill.

CodeGuard guidance informed bounded framing, fail-closed completion checks,
secret-free fixtures, suppressed diagnostics, retained Docker isolation and
SHA-256 artifact pinning. No credentials or certificates were introduced or
authentication settings changed. The skill-creator workflow keeps acquisition
and migration decisions explicit and the build/protocol detail in a reference.
Issue #5/#6 Python fixes and Issue #8 agent-behavior evaluations are not included.

## Publication follow-up: LFS false positives (2026-10-22)

A manual pre-publication `scan_sensitive.py --staged` refused four source/test
files because the old substring check classified quoted LFS version text as
external-content pointers. No commit or push was made on that failed check.
After explicit approval to fix it, a test-first regression reproduced that
failure and showed that the two historical version URLs were not refused.

Python, the Gitleaks adapter, and the Go runner now recognize standalone version
header lines, including the legacy URLs, CRLF and surrounding whitespace.
Truncated and malformed pointer-like metadata remains incomplete; quoted source
text receives the normal secret checks. A source fixture with an added inert
private-key canary is rejected, including through actual Git commit invocation.
Fenced examples containing standalone headers remain conservatively refused,
as documented in [limitations.md](../references/limitations.md#lfs-pointer-recognition).

The updated runner SHA-256 is
`13483d25dc5c1f110b35e8f70aca21e0fa6aec1783d4fc406d2ea186d005982e`.
The pinned offline build helper reproduced that digest in an independent build
directory. Runtime pins and acquisition documentation use this new artifact;
the previous section's digest and performance measurements describe the earlier
artifact, not a new benchmark of this one.

Using the full command above with the updated runner, all **92 tests passed with
no skips** in 245.705 seconds, including the real Docker lifecycle and legacy
migration. The five dedicated LFS tests also passed separately; Go's four runner
tests and controlled-github's 30 tests passed. All three skills passed structural
validation; Python syntax, local documentation links, and diff whitespace passed.
Before this fix, the pre-publication rerun had passed 86 tests after an initial
sandbox Docker-socket denial; that initial failed run was not a passing result.

CodeGuard informed retained refusal of external content, inert test data,
non-sensitive output, and SHA-256 pin verification; no credentials, certificates,
authentication settings, or target hook configuration were introduced. The
skill-creator check covers packaging, not agent behavior. Other Python scanner
issues and the outstanding agent-behavior evaluations remain outside this fix.

## Static images and publication budgets (2026-10-22)

Validation uses a temporary, hash-pinned CPython 3.10 environment with Pillow
12.3.0, pillow-heif 1.8.1 and defusedxml 0.7.1. The decoder capability check passed.
All images are synthetic; no personal image corpus is read. The existing runner
digest `13483d25dc5c1f110b35e8f70aca21e0fa6aec1783d4fc406d2ea186d005982e`
is unchanged: validated raster bytes never enter its text-only protocol.

The image/publication suite covers all eight format families, extension mismatch,
corrupt input, animation/multipage refusal, image size/pixels, missing codecs,
restricted SVG, secret-bearing SVG/text/messages, unchanged index files,
commit boundaries and push unions/intermediate history/force updates. Real
combined hooks accept synthetic images at commit and push, reject canaries in
both engines, and reject a reused blob under a misleading extension.

The full suite is run with `SECRET_CHECKS_RUNNER`, `SECRET_CHECKS_GITLEAKS`,
`SECRET_CHECKS_DOCKER=1` and `SECRET_CHECKS_LEGACY=1`, using the prepared venv:

```sh
/approved/secret-checks-venv/bin/python -B -m unittest discover \
  -s skills/secret-checks/evals -p 'test_*.py' -v
```

Final result: **108 tests passed, no skips**, in 587.968 seconds, including real
combined/Docker image hooks, lifecycle, and legacy rollback. Skill structural
validation, syntax parsing of 19 Python files, local documentation links and
`git diff --check` also passed. These are local tests, not production deployment.

An intermediate run reported two assertion failures because symlink/submodule
refusals now use `ERROR policy unsupported-index` rather than the previous
`INCOMPLETE` marker. Both still exited 2; the assertions were updated to the
new fixed diagnostic. This intermediate run is not a passing result.

Combined/Docker benchmark, single local runs:

| Index files | Changed files | Text bytes | Seconds | Exit |
| --- | --- | --- | --- | --- |
| 10 | 1 | 376 | 3.729 | 0 |
| 236 | 1 | 8,874 | 5.530 | 0 |
| 500 | 1 | 18,906 | 8.826 | 0 |

The benchmark now creates an existing baseline and changes one path: staging
500 new paths would correctly exceed the commit publication budget. This
measures full-index text inspection, not image throughput or a latency SLA, and
is not directly comparable to previous all-new-file fixtures.

CodeGuard guidance informed decoder limits, fixed diagnostics, disabled XML
external resources, and hash-pinned dependencies. Skill-creator guidance kept
the implementation self-contained and detailed setup in a linked reference.
The temporary decoder venv and existing Docker images are retained; no shared
image/cache pruning is performed. Generated bytecode was moved out of the
checkout into the task's temporary directory and remains recoverable there.
No target hook activation, deployment to another repository, commit, push,
authentication change, OCR, PII detection, or independent agent evaluation is
part of this implementation.

## Commit Gitleaks scheduling default (2026-10-22)

The default dispatcher now runs Python at both commit hooks and both engines at
push. New installs select combined/Docker. `--commit-gitleaks on` enables both
commit checks; OFF never disables push checks. Updates preserve existing
schedules, including legacy ON; rollback uses the exact older bundle. No
installed skill or target repository is updated by this source change.

Test-first evidence: the new default-skip test failed on the prior dispatcher
because the missing Gitleaks child made commit exit 2. After implementation the
eight dispatcher tests passed. The status matrix still tests both engines at
push, including failures; the commit argument test explicitly opts into both.
The legacy all-hooks lifecycle and image tests now explicitly select ON rather
than silently weakening their original assertions. New lifecycle coverage checks
the new-install default, actual commits without a runner, push refusal, ON/OFF
selection, schedule preservation, rollback, and invalid options. Two additional
focused tests passed for default prerequisite refusal and non-executing legacy
schedule interpretation.

The full suite with runner/CLI artifacts and Docker/legacy opt-ins ran 111 tests
in 418.205 seconds: 110 passed, one failed, none skipped. The failed Python-only
fixture omitted `--engine python` and consequently hit the new combined runner
prerequisite. After correcting that fixture (no runtime change), all 14 tests in
`test_scan_sensitive.py` passed in 3.156 seconds. The two additional focused
schedule tests passed in 0.332 seconds. Thus all 113 distinct current tests have
passing evidence across these runs; the entire suite was not rerun after the
fixture-only correction. Docker ON/OFF scheduling, actual push refusal,
preservation, legacy migration, rollback and image checks passed in the full run.
Skill validation, local links, Python syntax and diff whitespace checks passed.

CodeGuard informed strict option combinations, digest-covered scheduling,
explicit skip reporting and retained fail-closed push behavior. Only synthetic
canaries are used; no credentials, certificates or authentication mechanisms are
introduced. Skill-creator guidance kept the setting in the existing manager and
its reference instead of adding a new configuration framework. Source-only work:
no deployment, commit, push or external issue mutation is performed.

## Limits of the evidence

Skill frontmatter/reference checks do not establish agent behavior. Independent
agent scenarios in [scenarios.md](scenarios.md) are NOT RUN. macOS, Windows native,
live GitHub protection, production load, organization-wide deployment, hostile
local users and arbitrary existing hook-manager integrations are NOT RUN.

The current repository's hooks/configuration have not been activated or changed.
The manager's probes validate the selected installed bundle in isolated
repositories; they do not make commits in the user's target to prove invocation.
