# Validation record

## Scope

The executable artifact is the local, read-only target checker. Git/GitHub writes
are documented procedures, not implemented commit/push/PR wrappers. This skill
has no runtime dependency on the source repository or on another skill.

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
