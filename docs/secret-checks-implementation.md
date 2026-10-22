# Secret checks implementation record

## Commit scheduling default

Scope: update this distributable skill only; do not deploy to ModelForge or
other installed copies. New installations default to combined/Docker, running
Python at pre-commit/commit-msg and both engines at pre-push. Preserve image and
publication policies. Explicit `--commit-gitleaks on` restores both commit
detectors; there is no push opt-out. Pin the schedule in bundle code, never
ambient target configuration. Updates preserve existing schedules (legacy ON);
explicit OFF migrates them. Rollback restores the original bundle policy.

Acceptance: default commits never launch Gitleaks, missing Gitleaks blocks push,
ON runs both commit detectors, updates/rollback preserve the chosen schedule,
invalid option combinations refuse, and probes validate the selected schedule.
Regression first: the new default-skip test failed because the old dispatcher
attempted the absent Gitleaks child (exit 2 instead of 0). Implementation and
documentation are complete. The full integration run passed 110 of 111 tests;
the remaining Python-only fixture still relied on the old default. After adding
its explicit Python engine selection, all 14 Python scanner tests passed.
Two additional default/legacy schedule tests passed separately. Docker scheduling,
ON/OFF lifecycle, update preservation and rollback passed in the integration run.
No runtime code changed after that run; no target deployment was performed.

## Static images and publication budgets

Accepted scope: allow validated static PNG, JPEG, WebP, BMP, GIF, TIFF, HEIC,
and a restricted, non-rendered SVG subset. Raster contents and metadata are not
secret-scanned; SVG remains text-scanned. No OCR, PII detection, per-image
approvals, implicit dependency installation, or target-repository activation.

Commit budget: 100 added/modified/renamed regular paths and 20 MiB of their full
index contents. Push budget: 500 distinct newly reachable blobs and 50 MiB,
unioned across updates; a new ref conservatively includes full reachability.
Deletion-only updates add no content. Preserve existing secret-scan scopes and
text limits. Images are limited to 5 MiB, 20 million pixels and one frame/page.

| Slice | Dependencies | Acceptance | State |
| --- | --- | --- | --- |
| I1 | None | Reproduce valid-image rejection and bulk-upload missing guard | Complete |
| I2 | I1 | Shared bounded decoder validation and restricted SVG checks | Complete |
| I3 | I1 | Commit/push budgets include intermediate history and multiple refs | Complete |
| I4 | I2, I3 | Both engines, managed bundles, diagnostics and rollback integrate | Complete |
| I5 | I4 | Isolated regression/integration tests and updated skill/docs | Complete |

Baseline: 92 tests ran, 35 artifact-dependent tests skipped, no failures
(19.164 seconds). Final evidence is recorded in
[validation.md](../skills/secret-checks/evals/validation.md). Existing
README/runner reference edits and the untracked Gitleaks walkthrough are retained.

Final verification: 108 tests passed with no skips in 587.968 seconds, including
real combined/Docker hooks and legacy rollback. The 10/236/500-entry text
benchmarks completed in 3.729/5.530/8.826 seconds (one changed path each).
Skill structure, Python syntax, local documentation links and diff whitespace
checks passed. No target installation or Git publication was performed.

Image decoding adds a trusted, explicitly prepared Python environment. Use pinned
Pillow/pillow-heif/defusedxml packages; fail closed when unavailable or different.
Decoder subprocesses receive only bytes and a fixed format ID, suppress native
diagnostics, disable core dumps and apply memory/CPU/wall-time limits. They are
not a sandbox against native decoder compromise. Gitleaks retains Docker-first
execution and its existing batch runner/protocol. No image rewriting is allowed.

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
