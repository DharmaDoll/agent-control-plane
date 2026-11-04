# Validation record

## Scope

The executable artifacts are the local target checker and the gh authentication/
storage metadata checker. Git/GitHub writes are documented procedures, not
implemented commit/push/PR wrappers. This skill has no runtime dependency on the
source repository or on another skill. The storage checker can contact the
selected GitHub host through gh; the automated suite substitutes a fake CLI.

## Reproduce

From this skill directory:

```sh
python3 -B -m unittest discover -s evals -p 'test_*.py' -v
```

Tests create temporary local Git repositories and remove their own fixtures.
They do not contact GitHub or access credentials. Test identifiers/configuration
and leak-detection markers are synthetic, not working credentials.

## Executed checks

Local implementation verification (2026-10-19): Python 3.10.4, Git 2.47.2,
GitHub CLI 2.95.0. CLI help was inspected, without authenticating or making
network calls.

Coverage includes HTTPS/SSH forms, optional `.git`, linked worktrees, target/root mismatch,
missing targets, multiple URLs, mirror mode, URL rewrites, unsupported syntax,
argument and diagnostic redaction, subprocess timeout/error handling, unchanged
repository bytes after PASS/BLOCKED, and running a copied standalone helper.
The fixed-SHA push recipe is also exercised against a disposable local bare
repository: an unreviewed later HEAD, configured extra push ref, and annotated
tag are not sent; upstream is not automatically configured.

Results:

- Automated local suite: 30 tests passed, including copied-skill link checks.
- Skill creator's `quick_validate.py`: passed. This is a development-time
  structural validator; its PyYAML dependency is not a skill runtime requirement.
- Documentation link check: 12 Markdown documents, 19 relative links, none missing.
- `git diff --check`: passed for tracked documentation changes.
- Local target helper on this repository: PASS for the expected HTTPS target;
  this made no network request and did not verify authentication.

The implementation follows CodeGuard's credential and injection guidance: no
real credentials are embedded or read, no shell is used for subprocesses, and
external diagnostics/raw URLs are withheld. It adds no cryptography or
certificate processing and does not change transport verification settings.
These checks are not agent-behavior validation or a full security audit.

## Not verified

- Agent compliance with [scenarios.md](scenarios.md).
- Live authentication, GitHub permissions, push, or PR creation/readback.
- Automatic discovery/installation in any agent product.
- Other operating systems or Git/Python versions beyond the local test environment.
- Isolation from malicious Git configuration, binaries, hooks, or concurrent changes.

No skill installation, credential configuration, repository rename, or commit/
push in the working repository was performed. Commits and pushes in tests are
limited to disposable local fixtures; no live GitHub write or PR was made.

## Credential-storage warning addition (2026-11-04)

Tested working change: new `scripts/check_auth_storage.py`, its synthetic
`evals/test_check_auth_storage.py`, and the preflight/reference documentation.
Baseline: all 30 existing tests passed before implementation. Test-first source
classification checks then failed for the missing plaintext/keyring/environment
classifications (assertion failures, not missing imports or tooling errors).

Results after implementation, on Python 3.10.4 / Linux:

- Full `python3 -B -m unittest discover -s skills/controlled-github/evals
  -p 'test_*.py' -v`: 52 tests passed, no skips (30 existing + 22 new).
- `quick_validate.py skills/controlled-github`: passed.
- `git diff --check`: passed.

New coverage includes plaintext source metadata for Unix/custom/Windows paths,
keyring and environment distinctions, unknown/missing sources, inactive-account
plaintext (also behind an active environment token), invalid active credentials
despite gh JSON exit 0, account/host mismatch, malformed/oversized output,
timeouts/missing CLI, bounded account counts, fixed diagnostic redaction,
shell-free metadata-only arguments, and unchanged parent environment.
A copied standalone helper is executed with a recording fake gh for PASS, WARN,
and BLOCKED; fixtures remain byte-for-byte unchanged. The fake emits a synthetic
stderr marker and the helper does not forward it. These are deterministic helper
tests, not evidence of agent compliance or OS keyring implementation quality.

Separate native-CLI smoke check: GitHub CLI 2.95.0 with Python 3.13.5, a fresh empty
GH_CONFIG_DIR, and an isolated environment containing no authentication variables.
The real metadata projection completed and returned `BLOCKED / NOT_AUTHENTICATED`
(helper exit 2), as expected. The initial smoke run also exposed gh's automatic
telemetry device-ID creation. The helper now disables telemetry in its child
environment; subsequent native smoke checks use isolated state/cache directories
and confirm no fixture files are generated. The generated ID from the initial
run was moved out of the worktree into a temporary directory, not committed.
No real token, login, repository publication, or
OS credential-store migration was involved. Authenticated native keyring/plaintext
checks and actual agent behavior remain NOT RUN; user-level installed skills were
not updated. Storage inspection is limited to metadata gh reports, not an audit
of all credential files or copies.

CodeGuard informed fixed/sanitized output, no credential retrieval by the helper,
no auth changes, shell-free invocation, and synthetic-only fixtures. No custom
cryptography/certificate processing or weakened TLS verification was introduced.
