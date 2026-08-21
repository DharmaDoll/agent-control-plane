# Design Principles

## 1. Probabilistic reasoning, deterministic enforcement

LLMs are valuable because they can interpret ambiguous intent and reason across incomplete information.

That same flexibility is undesirable for some execution decisions.

A useful separation is:

```text
Reasoning plane:
  "What does the user want?"
  "Which operation is appropriate?"
  "Which files are relevant?"

Control plane:
  "Which command performs the write?"
  "Which credential source is allowed?"
  "Which target may be modified?"
  "Which preconditions must hold?"
  "What is forbidden?"
```

The reasoning plane may be probabilistic.

Security-sensitive enforcement should be deterministic wherever practical.

---

## 2. Do not delegate unnecessary implementation choices

The motivating GitHub example is simple.

A human requests:

> commit and push

The desired state is clear.

But an unconstrained agent may independently decide:

```text
git push
gh ...
SSH
HTTPS
PAT
credential helper
environment token
remote rewrite
authentication retry
```

That is unnecessary implementation freedom.

The problem is not merely that the model may choose a "wrong" command.

The deeper issue is that **the implementation strategy itself has become part of the model's probabilistic reasoning**.

That creates:

- inconsistent behavior;
- unpredictable credential access;
- difficult incident reconstruction;
- larger attack surface;
- hard-to-test workflows;
- agent-specific behavior;
- brittle recovery logic.

A control-plane design removes choices that do not need to be choices.

---

## 3. Minimize the agent-facing interface

Prefer:

```text
agent -> approved operation -> system
```

over:

```text
agent -> unrestricted shell/API surface -> system
```

Examples of narrow interfaces:

```text
repo-check
repo-commit --paths ...
repo-push
deploy-staging
rotate-preview
read-production-logs
```

A narrow interface can enforce assumptions before touching the target system.

---

## 4. Keep credentials below the reasoning boundary

Possession of authority does not imply visibility of credentials.

An agent may be allowed to run:

```bash
git push
```

without being allowed to see the token used by the credential helper.

Prefer:

```text
Agent
  |
  v
Authenticated CLI
  |
  v
Credential broker / OS keychain / workload identity
```

Avoid:

```text
Agent
  |
  v
Raw token
  |
  v
External API
```

This reduces accidental disclosure, prompt-injection impact, logging exposure, and credential handling complexity.

---

## 5. Fail closed instead of creatively recovering

Agents are often optimized to complete tasks.

For privileged operations, that can be dangerous.

Example:

```text
HTTPS authentication fails
        |
        +--> BAD: try SSH
        |
        +--> BAD: inspect token files
        |
        +--> BAD: rewrite remote
        |
        +--> BAD: disable verification
        |
        `--> GOOD: stop and report
```

A failure should not implicitly authorize a different security posture.

---

## 6. Separate policy, procedure, and mechanism

A useful structure is:

```text
AGENTS.md / policy
        |
        v
Skill / procedure
        |
        v
CLI or wrapper / mechanism
```

### Policy

Defines constraints and allowed behavior.

Example:

> Never expose GitHub access tokens.

### Procedure

Defines an approved workflow.

Example:

> Check repository, branch, remote, authentication, and diff before push.

### Mechanism

Performs the operation.

Example:

```bash
git push -u origin HEAD
```

Keeping these separate makes the system easier to review and evolve.

---

## 7. Use existing trusted control points

Do not build custom infrastructure when the platform already provides a strong security boundary.

Examples:

- OS keychains
- Git credential helpers
- GitHub CLI
- cloud workload identity
- Kubernetes RBAC
- IAM roles
- CI environment protection rules

The control plane should compose trusted primitives before replacing them.

---

## 8. Human approval should protect meaningful boundaries

Human approval is useful, but approving every shell command creates noise.

Place approval gates around meaningful transitions such as:

```text
local change -> commit
commit -> remote push
build -> production deployment
read -> write
non-privileged -> privileged
```

This provides better security than indiscriminate confirmation dialogs.

---

## 9. Make privileged operations observable

At minimum, a privileged workflow should make it possible to answer:

- What did the agent intend to do?
- What command or approved interface was used?
- What target was affected?
- What files/resources changed?
- Which identity authorized the action?
- Did preconditions pass?
- Did the operation succeed?

Auditability should be designed into the interface.

---

## 10. Keep the model replaceable

A security control that only works because one specific model usually "behaves well" is fragile.

Prefer designs that survive replacement of:

- Codex
- Claude Code
- Gemini CLI
- Cursor
- future agents

The control plane should remain useful even as the reasoning engine changes.
