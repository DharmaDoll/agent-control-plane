# GitHub control pattern — extracted

The former example is now the standalone
[controlled-github skill](../../skills/controlled-github/SKILL.md).
Its [local target checker](../../skills/controlled-github/references/target-check.md)
and [operation recipes](../../skills/controlled-github/references/operations.md)
are the canonical implementation.

The motivating problem remains an agent expanding “commit and push” into token
retrieval, remote rewriting, or authentication changes. The skill keeps credentials
in the approved CLI/helper path and checks the local destination deterministically.

This is not a sandbox: trusted binaries, configuration, hooks, host permissions,
and GitHub protection rules remain necessary. Do not use it to isolate an
untrusted execution environment or to authorize unattended privileged operations.
