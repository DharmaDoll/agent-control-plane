# Secret checks implementation record

## Accepted scope

Make this repository the canonical home of the Python scanner and Gitleaks
adapter from product-security-guidance. Ship one self-contained skill with local
diagnosis, versioned installation, verification, update/rollback, uninstall and
cleanup. The guidance repository retains architectural decisions and links to
the implementation. Keep actual repository hook activation separate from building
the skill; all executable tests use disposable repositories.

## Acceptance criteria and work

| Task | Dependencies | Observable completion condition | State |
| --- | --- | --- | --- |
| T1: migrate scanners/tests | None | Original Python behavior preserved; pinned Gitleaks tested | Complete |
| T2: diagnose environments | T1 | Read-only inspection routes ordinary, configured, incomplete and shared repos | Complete |
| T3: manage bundles | T2 | Tested installation, idempotence, updates, rollback and config restoration | Complete |
| T4: verify behavior | T3 | Actual local Git accepts safe operations and refuses findings/incomplete input | Complete |
| T5: cleanup | T3 | Preview; active/previous protected; only recorded matching files removed | Complete |
| T6: skill/docs | T1–T5 | Self-contained instructions, commands, scope and evidence | Complete |
| T7: guidance references | T1–T6 | Existing entrypoints link here and no longer maintain duplicate scanner code | Complete locally; publication pending |

## Baseline and decisions

- Source: product-security-guidance commit `2b5e81df0eee973d4cc4fc493fe09d93d207ea0b`.
- Original Python suite: 8 tests passed before migration.
- Local preinstalled Gitleaks did not match the pinned binary; acquired official
  8.30.1 in a temporary directory and verified archive/binary digests before use.
- Linux/WSL2 and Python 3.10+ are the initial supported environment. Existing hook
  chains and shared worktrees receive a concrete integration diagnosis, not an
  automatic rewrite. Gitleaks is explicitly selected, never a fallback.
- Manager uses standard-library Python and existing Git. No framework, package
  dependency, watcher, credentials or SaaS configuration was introduced.
- Cleanup keeps a minimal management record and lock for audit/repeated runs.
- Changes from source: isolated Python invocation, absolute Git/interpreter,
  sanitized Python diagnostics, branch-only Python push scope, bounded/incomplete
  handling, versioned management and actual local Git probes.

## Verification and remaining work

See [validation.md](../skills/secret-checks/evals/validation.md) for commands,
suite-specific evidence and limitations. The initial whole-suite run passed 52
tests; the final inventory refinement adds one manager scenario. Inherited tests
remain applicable to the unchanged Gitleaks adapter; affected manager/Python
suites were rerun after their last changes. Independent agent scenarios and
production/SaaS behavior remain unverified.

Source guidance now has reference stubs instead of 12 duplicate implementation
files, updated Makefile targets and a migration entry. Its offline check reports
3,421 local links, 54 unique control IDs and zero errors. Existing unrelated
guidance edits and the local `skills_plan/` drafts were preserved.

No commits, pushes, repository hook activation or SaaS configuration changes were
made. Publish agent-control-plane first, then the guidance reference changes;
external links to the new skill become available only after publication. Removed
source files remain recoverable from the source repository's Git history.
