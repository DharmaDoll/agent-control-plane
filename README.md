# agent-control-plane

A practical repository for designing, discussing, and implementing safe, deterministic, and auditable AI agent operations.

## Why this repository exists

A recurring failure mode in AI coding agents is giving the agent too much freedom over **how** privileged operations are performed.

For example, a user may say:

> "Commit and push these changes."

If the agent is allowed to decide the implementation method every time, it may reason differently on each run:

- use `git push`
- use `gh`
- switch from HTTPS to SSH
- look for a token in environment variables
- inspect credential files
- rewrite the Git remote
- retry with a different authentication mechanism

The user's intent is stable, but the execution path is not.

This creates a fundamental problem:

> **We are asking a probabilistic system not only to decide what should be done, but also to invent how privileged operations should be executed.**

That makes behavior harder to predict, audit, secure, and debug.

The purpose of `agent-control-plane` is to separate these responsibilities.

```text
Probabilistic reasoning
        |
        v
Policy-constrained decision
        |
        v
Deterministic interface
        |
        v
Least-privileged credential boundary
        |
        v
External system
        |
        v
Verification / Audit
```

The agent can still reason about **what action is appropriate**.

The control plane defines **how that action is safely executed**.

## Core idea

Do not rely on an LLM being consistently clever about privileged operations.

Instead:

1. define policy explicitly;
2. expose a small number of approved interfaces;
3. make sensitive execution deterministic;
4. keep credentials outside the agent's reasoning context;
5. fail closed when assumptions are violated;
6. make writes observable and auditable.

In short:

> **Probabilistic reasoning, deterministic enforcement.**

## Initial use case: Git and GitHub

The first reference use case is Git/GitHub operations from coding agents such as Codex CLI or Claude Code.

The intended model is:

```text
Agent
  |
  v
AGENTS.md
  |  policy
  v
Skill / approved workflow
  |  procedure
  v
git / gh / wrapper
  |  deterministic execution
  v
OS credential store
  |
  v
GitHub
```

Important principles:

- Git operations use `git`.
- GitHub-specific operations use `gh`.
- Authentication configuration is managed outside the agent workflow.
- Agents must not retrieve or print access tokens.
- Agents must not silently switch authentication methods.
- Agents must not rewrite remotes to work around authentication failures.
- Writes should be preceded by status/diff/preflight checks.
- Staging should target explicit paths.
- Failures should be reported instead of "creatively" bypassed.

See [`docs/principles.md`](docs/principles.md) and [`examples/github/README.md`](examples/github/README.md).

## Repository scope

This repository is intentionally not GitHub-specific.

Future patterns may cover:

- GitHub
- AWS
- GCP
- Kubernetes
- Terraform
- CI/CD
- Slack
- databases
- internal APIs
- SaaS administration
- MCP servers
- agent skills and plugins

The common question is:

> Where should agent reasoning end, and deterministic control begin?

## How this repository should evolve

When a new problem appears:

1. capture the failure mode;
2. identify which decision was unnecessarily delegated to the agent;
3. define the security boundary;
4. turn the lesson into a reusable principle or pattern;
5. implement the smallest deterministic interface that solves it;
6. document trade-offs and exceptions.

The repository should become a practical body of knowledge for operating increasingly capable agents safely.

## Initial structure

```text
agent-control-plane/
├── README.md
├── AGENTS.md
├── docs/
│   └── principles.md
└── examples/
    └── github/
        └── README.md
```

The structure is intentionally small. Add new directories only when repeated use cases justify them.
