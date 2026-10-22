---
name: secret-checks
description: Inspect a local Git repository and install, verify, update, roll back, uninstall, or clean up deterministic secret-check hooks. Use when setting up or troubleshooting checks before commit or push. Detection runs through Git hooks, independently of the agent.
---

# Secret checks

Set up repository-local secret checks using the bundled scanner and standard Git
hooks. This directory is the canonical, self-contained implementation. Requires
Linux (including WSL2), Git at `/usr/bin/git`, Python 3.10+, and POSIX shell.

## Start from the request and local evidence

1. Establish the target repository root and requested operation. An inspection
   request authorizes inspection; an installation request covers normal setup
   and verification. Keep an existing installation's engine unless a switch is
   requested. The initial default is the standard-library Python scanner.
2. Run the manager below with `inspect`. It reports clone/worktree limitations,
   existing hook conflicts, configuration scope, active version, and a suggested
   next step without modifying the repository.
3. Follow the result. For an ordinary repository with no existing hooks, use
   `install`. For an existing managed installation, use `verify` or `update`.
   Read [installation.md](references/installation.md) for commands, integration,
   update/rollback, cleanup, and recovery.

```sh
python3 -B <skill-dir>/scripts/manage_hooks.py inspect --repo /absolute/repository/root
```

An existing hook or hook manager needs a concrete integration proposal: preserve
the existing behavior, arguments, pre-push stdin, and failure propagation. Do not
replace it or invent an automatic chain. Shared worktrees require an explicitly
reviewed installation design; the initial automatic installer stops for them.

## Execute and verify

Use `scripts/manage_hooks.py` for management; never synthesize an installer or
cleanup command. It prepares a versioned bundle, runs real Git probes in temporary
repositories, then changes only the target's local `core.hooksPath` and reads it
back. It records file digests, activation state, and the original absence of hook
configuration. The installed hooks do not depend on this checkout or a network.

For Gitleaks or combined mode, read the deployment and acquisition procedure in
[gitleaks.md](references/gitleaks.md) before setup. Distinguish skill-copy
installation from executable acquisition and hook activation. Establish the
engine, supported OS/architecture, approved binary source and staging path, and
target Git administration directory. Prefer Docker for new Gitleaks/combined
installations and pass `--runtime docker` explicitly. Read
[docker.md](references/docker.md) for daemon prerequisites, image preparation,
execution limits, and retained-image cleanup. Use `--runtime native` only when
the user selects it; an unavailable Docker daemon is not permission to fall back.
Preserve an existing runtime unless a change is requested. The manager never downloads
software or substitutes a different engine after failure. The batch runner is a
separate, digest-pinned executable: supply `--gitleaks-runner`, not the official
CLI's `--gitleaks` path. Existing pre-batch installations need an explicit runner
input on their first update. Read [runner.md](references/runner.md) for approved
offline builds and the batch protocol; do not build or acquire during a hook.
If the pinned binary
or an approved acquisition procedure is unavailable, report that specific blocker.
Do not invent a downloader, install Docker/packages, use `sudo`, modify PATH, or
substitute a binary found on PATH as an implicit setup step.

When both scanners are requested, select `--engine combined` and read
[combined.md](references/combined.md). Every hook runs Python then Gitleaks and
requires both to succeed. Both engines' limitations apply; do not promise zero
leaks or silently convert an existing installation.

For an explanation of the Python engine's normal commit path, read
[python-hook-flow.md](references/python-hook-flow.md). It traces Git's hook
selection, index/message inspection, refusal behavior, and verification limits.

Use `verify` after setup or when investigating drift. Report configuration,
bundle integrity, and isolated hook behavior separately. The probe tests safe
commit/push, staged secrets, message secrets, unscannable input, and a secret that
was removed from the latest tree but remains in outgoing history. It changes
neither the target's index/history nor any external remote.

## Cleanup and failure handling

`cleanup` previews candidates. Add `--apply` when cleanup is requested and the
reported scope matches that request. It removes only recorded, unchanged files;
it retains the active and previous bundles, unknown files, modifications, and
symlinks. `uninstall` restores the original absence of the local hook setting;
run cleanup afterward when removal of the retained bundles is requested.

Treat findings, errors, incomplete checks, and unknown management state as stops.
Do not bypass hooks, add blanket exclusions, or change detection engines to get a
commit/push through. Do not ask for secret values or paste scanner payloads into
chat. If exposure has already occurred, hand off credential revocation and
incident investigation; deleting a file is not containment.

## Scope and evidence

Read [limitations.md](references/limitations.md) before recommending an engine or
interpreting a pass. Local hooks are user-controlled and bypassable. They do not
configure GitHub push protection, protect Web/API writes, or prove the absence of
all secrets. Existing Git configuration, installed code, interpreters, and the
local account remain trusted.

Use [scenarios.md](evals/scenarios.md) for agent-behavior evaluations. Automated
tests and their recorded scope are in [validation.md](evals/validation.md).
Report the engine and runtime, skill location, binary source, Docker image ID
when applicable, resolved installed binary/hook paths, bundle ID, actual checks/results, retained
cleanup items, and any unsupported configuration. Do not disclose sensitive path
components in public documentation; use placeholders there. A suggested integration is not an installed or
verified integration. Commit/push and SaaS configuration are separate operations.
