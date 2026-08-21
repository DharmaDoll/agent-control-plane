# GitHub Authentication Setup

This document defines the initial authentication setup for local agent-driven
GitHub operations.

The initial supported configuration is deliberately narrow:

```text
HTTPS Git remote
        |
        v
Git credential helper
        |
        v
GitHub CLI (`gh`)
        |
        v
OS credential store
```

SSH, environment-provided tokens, GitHub Enterprise, and CI authentication are
outside the initial scope. They should be documented as separate configurations
if they are needed later.

## Responsibility boundary

Authentication setup is a human-administered operation.

An agent may check the existing authentication state, but it must not:

- sign in to or out of GitHub;
- retrieve or print a token;
- change the Git protocol;
- rewrite a Git remote;
- create or upload an SSH key;
- choose a different authentication method after a failure.

## Prerequisites

Install `git` and the [GitHub CLI](https://cli.github.com/). Ensure that the OS
has a working credential store before continuing.

## One-time human setup

Run the interactive browser login explicitly for `github.com` and HTTPS:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

GitHub CLI normally stores the resulting credential in the system credential
store. If a credential store is unavailable, `gh` may fall back to a plain-text
file. Do not treat setup as complete in that case. Configure an appropriate OS
credential store, then repeat the login.

Configure Git to use GitHub CLI as the credential helper for `github.com`:

```bash
gh auth setup-git --hostname github.com
```

This changes Git authentication configuration and must not be run automatically
by an agent.

## Verification

Verify the active GitHub account without displaying its token:

```bash
gh auth status --active --hostname github.com
```

Never add `--show-token` to this command.

Inside each repository, verify that `origin` uses the supported HTTPS form:

```bash
git remote get-url origin
```

The expected form is:

```text
https://github.com/OWNER/REPOSITORY.git
```

If the remote is missing, targets a different host, or uses SSH, stop. A human
must decide whether to reconfigure the repository. The agent must not run
`git remote set-url` as a recovery step.

## Failure behavior

If login, credential storage, account identity, hostname, or remote protocol is
uncertain, do not perform a GitHub write. Report the failed check without trying
another authentication method.

Official references:

- [`gh auth login`](https://cli.github.com/manual/gh_auth_login)
- [`gh auth setup-git`](https://cli.github.com/manual/gh_auth_setup-git)
- [`gh auth status`](https://cli.github.com/manual/gh_auth_status)
