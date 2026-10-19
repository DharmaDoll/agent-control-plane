# AGENTS.md

## Purpose

This repository is a personal collection of Product Security skills, including
the operational workflows that support that work. Keep the repository name
`agent-control-plane` until a rename is explicitly requested.

Optimize for:

1. safety,
2. deterministic execution,
3. simplicity,
4. auditability,
5. portability across agent products.

Do not add abstraction solely because an agent framework supports it.

## Repository philosophy

A central design principle is:

> Do not make a probabilistic agent invent the execution mechanism for privileged operations when the mechanism can be made deterministic.

The agent should primarily decide **what should happen**.

Policies, approved commands, scripts, skills, MCP tools, or other control-plane mechanisms should define **how sensitive actions happen**.

When evaluating a design, ask:

- Is the agent being asked to make an unnecessary implementation choice?
- Can that choice be encoded deterministically?
- Can credentials remain outside the agent's visible context?
- Can the operation fail closed?
- Can a human understand exactly what happened afterward?
- Is the interface smaller than the underlying system it controls?

## Development rules

Keep the repository simple while the design is still evolving.

- Put distributable skills under `skills/<skill-name>/` with a concise `SKILL.md`.
- Make each skill self-contained; use relative references within its directory.
- Load detailed references only when needed; do not duplicate canonical procedures.
- Prefer standard-library scripts; add shared infrastructure only for demonstrated reuse.
- Keep README.md in Japanese; keep skill instructions, technical docs, and code in English.
- Test helpers with isolated local fixtures. Separate automated results, agent-behavior
  evaluations, and live-service checks; never claim unexecuted validation passed.
- Treat `skills_plan/` as draft source, not a runtime dependency or distribution.
  Preserve existing untracked drafts unless the user explicitly requests changes.

Prefer:

- Markdown for design and decision records.
- Small scripts over large frameworks.
- Existing trusted CLIs over custom API clients.
- Explicit command boundaries.
- Read-only inspection before write operations.
- Least privilege.
- Idempotent or safely retryable operations where possible.

Avoid:

- unnecessary dependencies;
- opaque orchestration;
- credentials in repository files;
- tokens printed to stdout;
- agent-generated authentication workarounds;
- hidden side effects;
- automatic privilege escalation;
- broad write operations when narrow ones are available.

## Security boundary

Secrets and credentials should normally be managed outside the repository and outside the agent's reasoning context.

Examples:

- OS credential stores
- workload identity
- short-lived credentials
- Git credential helpers
- cloud-native identity mechanisms

An agent may invoke an authenticated tool without needing direct access to the underlying secret.

## Failure behavior

For privileged operations, prefer fail-closed behavior.

If authentication, authorization, repository identity, target environment, or expected preconditions are uncertain:

1. stop the write operation;
2. report the exact failure;
3. do not invent a new authentication method;
4. do not weaken security controls;
5. do not silently change the target.

## Git safety for this repository

Before modifying files:

```bash
git status --short
```

Before committing:

```bash
git diff
git diff --cached
```

Stage explicit paths only.

Do not use:

```bash
git add .
git add -A
git add --all
```

unless a human explicitly requests that exact behavior and the scope has been verified.

Do not commit, push, force-push, create a PR, merge, or alter authentication configuration unless explicitly requested.

## Documentation changes

When introducing a new control pattern, document:

- problem;
- unsafe or unstable behavior;
- trust boundary;
- deterministic mechanism;
- residual risks;
- when the pattern should not be used.

Prefer concrete examples over abstract framework language.
