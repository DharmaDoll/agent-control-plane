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
