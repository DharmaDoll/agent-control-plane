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

Tests use only temporary local worktrees/bare remotes and runtime-assembled,
non-issued canaries. No real credential, live GitHub push or target-checkout
commit is used.

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

## Limits of the evidence

Skill frontmatter/reference checks do not establish agent behavior. Independent
agent scenarios in [scenarios.md](scenarios.md) are NOT RUN. macOS, Windows native,
live GitHub protection, production load, organization-wide deployment, hostile
local users and arbitrary existing hook-manager integrations are NOT RUN.

The current repository's hooks/configuration have not been activated or changed.
The manager's probes validate the selected installed bundle in isolated
repositories; they do not make commits in the user's target to prove invocation.
