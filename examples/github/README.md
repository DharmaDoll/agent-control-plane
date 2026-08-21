# GitHub Control Pattern

This directory documents the first reference pattern for `agent-control-plane`.

It is intentionally small.

## Problem

A coding agent receives:

> commit and push

Without constraints, the agent may choose a different GitHub access strategy from run to run.

Possible behavior includes:

- `git push`
- GitHub CLI
- HTTPS
- SSH
- environment tokens
- credential inspection
- remote rewriting
- alternative authentication retries

This creates security and reliability problems.

The user requested a state transition, not a new authentication architecture.

## Desired boundary

```text
Agent reasoning
    |
    | decides:
    | - whether a commit is appropriate
    | - which files belong to the change
    | - what commit message is appropriate
    v
Approved Git workflow
    |
    | enforces:
    | - repository validation
    | - explicit staging
    | - authentication preflight
    | - fixed remote behavior
    | - fixed push behavior
    | - fail-closed semantics
    v
git / gh
    |
    v
Credential helper
    |
    v
OS credential store
    |
    v
GitHub
```

## Recommended responsibility split

| Operation | Preferred mechanism |
|---|---|
| status | `git` |
| diff | `git` |
| add | `git` |
| commit | `git` |
| branch | `git` |
| fetch/pull/push | `git` |
| authentication health | `gh auth status` |
| pull request | `gh pr` |
| issue | `gh issue` |
| GitHub API | `gh api` |

The important point is not that these commands are universally mandatory.

The important point is that the workflow chooses a convention **once**, instead of asking the agent to rediscover it every time.

## Authentication model

Recommended local-agent model:

```text
git
 |
 v
Git credential helper
 |
 v
GitHub CLI / OS credential storage
 |
 v
GitHub
```

The agent should not need to retrieve the underlying token.

### Forbidden recovery behavior

If authentication fails, the agent should not automatically:

- run `gh auth token`;
- inspect credential files;
- search shell history for PATs;
- embed credentials in Git remotes;
- switch HTTPS to SSH;
- switch SSH to HTTPS;
- create a new credential;
- disable certificate or host verification.

Stop and report the failure.

## Preflight

Before a GitHub write:

```bash
git rev-parse --show-toplevel
git status --short
git branch --show-current
git remote get-url origin
gh auth status --hostname github.com
```

Then inspect the relevant diff.

## Staging

Prefer:

```bash
git add -- path/to/file1 path/to/file2
```

Avoid broad staging:

```bash
git add .
git add -A
git add --all
```

The agent should identify the intended change set before creating a commit.

## Push

A simple standardized push policy is:

```bash
git push -u origin HEAD
```

or another repository-defined convention.

What matters is that the policy is predetermined.

Authentication failure must not cause the agent to invent a new push path.

## Next step

Once this pattern stabilizes, it may be implemented as:

```text
Skill
  +
small wrapper scripts
```

For example:

```text
github-check
github-commit
github-push
github-pr
```

Do not add wrappers until they reduce real repeated ambiguity or risk.

This repository intentionally starts with the design boundary first.
