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
