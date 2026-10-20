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

## Limits of the evidence

Skill frontmatter/reference checks do not establish agent behavior. Independent
agent scenarios in [scenarios.md](scenarios.md) are NOT RUN. macOS, Windows native,
live GitHub protection, production load, organization-wide deployment, hostile
local users and arbitrary existing hook-manager integrations are NOT RUN.

The current repository's hooks/configuration have not been activated or changed.
The manager's probes validate the selected installed bundle in isolated
repositories; they do not make commits in the user's target to prove invocation.
