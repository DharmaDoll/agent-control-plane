# GitHub Agent Workflow

This document defines the initial Git and GitHub command sequence for a local
coding agent. It uses existing `git` and `gh` commands directly. There are no
repository-specific wrapper commands in the initial implementation.

Complete the human-administered [authentication setup](setup.md) before using
this workflow.

## 1. Preflight

Before a commit, push, or pull request, run:

```bash
git rev-parse --show-toplevel
git status --short
git branch --show-current
git remote get-url origin
gh auth status --active --hostname github.com
```

Confirm that:

- the repository root is the expected repository;
- the current branch is named and is not a detached `HEAD`;
- `origin` is the expected `https://github.com/OWNER/REPOSITORY.git` remote;
- the active GitHub account is the intended account;
- all working-tree and staged changes are understood.

Stop if a check fails or its result is ambiguous. Do not repair authentication
or repository configuration as part of the requested GitHub write.

## 2. Review and stage explicit paths

Inspect both existing staged changes and the intended unstaged changes:

```bash
git diff --cached
git diff -- path/to/file1 path/to/file2
```

If the index already contains unrelated changes, stop and report them. Do not
unstage or overwrite another change set without an explicit request.

Stage only the intended paths:

```bash
git add -- path/to/file1 path/to/file2
```

Review the complete staged result before committing:

```bash
git status --short
git diff --cached
```

Do not use broad staging commands such as `git add .`, `git add -A`, or
`git add --all`.

## 3. Commit

Create the commit only after the staged diff has been reviewed:

```bash
git commit -m "Describe the intended change"
```

Then inspect the resulting commit:

```bash
git show --stat --oneline HEAD
```

## 4. Push

Repeat the branch, remote, and authentication checks immediately before a push:

```bash
git branch --show-current
git remote get-url origin
gh auth status --active --hostname github.com
```

Use the fixed push form:

```bash
git push -u origin HEAD
```

Do not force-push, select another remote, rewrite the remote, or switch
authentication methods in response to a failure.

## 5. Create a pull request

Use GitHub CLI after the branch has been pushed:

```bash
gh pr create \
  --base main \
  --head branch-name \
  --title "Pull request title" \
  --body-file path/to/body.md
```

Replace `main`, `branch-name`, and the body path with reviewed explicit values.
Do not rely on an interactive prompt to choose the base or head branch.

## Authentication commands

The agent may run this read-only authentication check:

```bash
gh auth status --active --hostname github.com
```

The agent must not run authentication or credential-changing commands,
including:

```text
gh auth login
gh auth logout
gh auth token
gh auth status --show-token
gh auth setup-git
git remote set-url ...
```

Authentication failure closes the workflow. It does not authorize a different
credential source or transport.
