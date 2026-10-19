# Human-managed authentication setup

This is a separate human task, never an agent's automatic recovery procedure.
The recommended personal setup is HTTPS Git with `gh` as its credential helper.
An already approved SSH setup may be used without switching transports; SSH key
enrollment is outside this guide. The helper accepts either transport but does
not authenticate it.

## Prerequisites and choices

Install Git, Python 3.10+, and GitHub CLI. Decide the GitHub host, intended account,
owner/repository, transport, remote name, and branch policy. Prepare a working OS
credential store. Select only the repository permissions needed for the intended
operations; account login alone does not grant repository or branch write access.
Organization authorization and branch protection remain independently enforced.

## One-time HTTPS setup (human terminal)

For `github.com`, run interactively:

```sh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
gh auth status --active --hostname github.com
```

Never add `--show-token` or use `gh auth token`. Check the intended active account
and secure credential storage. If `gh` reports plaintext credential storage,
do not accept setup as complete: configure an OS credential store and repeat
the login. Do not paste tokens into chats, files in this repository, or remotes.
For another approved host, substitute that host consistently; do not silently
reuse `github.com` or another account.

`setup-git` changes Git authentication configuration. The human should review
its scope and any existing credential-helper arrangement before running it.
No runtime skill operation should repeat this configuration step.

The human separately configures the repository's remote to the agreed HTTPS
destination, without credentials embedded in its URL. Run the
[local target check](target-check.md) with the agreed values to verify it.
Do not change a remote solely because an operation failed.

## Verification and failures

The active `gh` account check verifies CLI authentication, not Git's actual
credential route or write authority. Validate the approved Git route with a
read-only `git ls-remote` against the checked remote; public read access alone
does not prove which identity will authorize a push. Keep the expected credential
route documented in trusted project instructions when needed. A local commit
needs neither login nor network access.

Distinguish host/sandbox network denial from credential rejection. Use only the
host-approved diagnostic path. Missing permissions, unclear identity, or failed
authentication require human action; never weaken TLS, SSH verification, hooks,
or branch rules. Credential values must remain outside the agent's context.

The installed CLI's `gh auth login --help`, `gh auth setup-git --help`, and
`gh auth status --help` describe its supported flags and storage behavior.
