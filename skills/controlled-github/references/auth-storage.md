# Authentication and credential-storage check

## Purpose and boundary

`gh auth login` can fall back to plaintext token storage when the OS credential
store is unavailable. Successful authentication alone does not establish safe
storage. This check makes that distinction visible without letting an agent
retrieve a token or inspect credential files.

Use it before `gh` operations and before HTTPS Git operations when the already
approved helper is `gh`. Do not infer that route merely from HTTPS or a previous
successful push. Do not require it for a local-only commit, SSH-only Git, or a
different approved helper. It is a procedure-time check, not a watcher or hook.

From the skill directory, substitute the independently established host/account:

```sh
python3 -I -B scripts/check_auth_storage.py --host github.com --account EXPECTED_LOGIN
```

Run the existing target check first for repository-bound network operations.
The helper uses the trusted `gh` on PATH and its existing authentication/config
path. It invokes `gh auth status --hostname <host> --json hosts` with a fixed,
built-in `--jq` projection of `host`, `login`, `active`, `state`, and `tokenSource`.
No separate jq dependency is needed. It does not pass `--active`, so reported
inactive accounts on that host also contribute storage warnings. Other hosts
are not inspected. `gh` performs normal network authentication checks: this is
not an offline checker. In JSON mode, gh can exit 0 despite authentication errors,
so the helper validates the structured state and expected active account too.

No `--show-token`, token command, direct credential-file/keyring read, shell,
login, logout, refresh, or setup-git is used. `gh` itself accesses credentials for
authentication. Raw stdout, errors, token source paths, and account names are not
forwarded; the helper emits fixed enums only. Debugging/prompts/update notices/telemetry
are suppressed in the child environment without changing authentication variables
or persistent settings. The command has a 20-second timeout, a 128 KiB JSON limit
(checked after capture), and a 128-account parser limit.

## Results and required user notification

| Result / exit | Meaning | Agent action |
| --- | --- | --- |
| PASS / 0 | Expected active account authenticated; reported sources are keyring | Continue only within the existing authorization. This is not a general security certification. |
| WARN / 1 | Active authentication passed, but storage needs attention | Explain warnings before the operation and repeat them in the final report. Do not silently label this PASS. Continue if existing policy permits; warning alone is not a new approval gate. |
| BLOCKED / 2 | Authentication/account cannot be established or check failed | Stop the affected authenticated operation; report the fixed reason and any storage warnings. Do not change auth or fall back to raw output. |

The output separates `authentication` from `active_storage`. Warnings include
all accounts reported for that host, even when an inactive token is invalid.
Inactive-account authentication does not establish or invalidate the active
identity. Storage warnings survive a failed active authentication check when
valid metadata is available.

| Warning | Interpretation and notification |
| --- | --- |
| `PLAINTEXT_CREDENTIAL_STORAGE` | gh reports a token sourced from `hosts.yml` or `oauth_token`. Tell the user plaintext credential storage was detected and recommend human-managed OS credential-store setup. Do not output the path or token, move/delete it, or reauthenticate automatically. |
| `ENVIRONMENT_STORAGE_NOT_VERIFIED` | A source is GH_TOKEN/GITHUB_TOKEN or an enterprise equivalent. This does not prove where that variable is stored. Explain that storage at rest is not verified; do not call it plaintext-file detection or keyring storage. |
| `CREDENTIAL_STORAGE_UNKNOWN` | Source metadata is missing or unrecognized. Say storage could not be determined; do not assume secure storage. |

Example for an authenticated active plaintext token:

```json
{"status":"WARN","reason":"AUTHENTICATED","authentication":"PASS","active_storage":"PLAINTEXT","warnings":["PLAINTEXT_CREDENTIAL_STORAGE"]}
```

Suggested notification, translated to the user's language:
"gh reports plaintext credential storage. No token was displayed and no
authentication settings were changed. Configure an OS credential store through
the human-managed setup procedure."

`AUTH_CHECK_FAILED` may represent a rejected token **or** a network failure; it
does not justify claiming invalid credentials. `AUTH_TIMEOUT`/`GH_TIMEOUT` means
the check did not complete. `ACCOUNT_MISMATCH`, `ACTIVE_ACCOUNT_AMBIGUOUS`, and
`NOT_AUTHENTICATED` require resolving identity. `GH_CHECK_FAILED`,
`UNSUPPORTED_GH_OUTPUT`, `GH_OUTPUT_TOO_LARGE`, `UNEXPECTED_HOST`,
`CHECK_UNAVAILABLE`, or `INVALID_ARGUMENTS` require resolving the reported check
failure. Use only the host-approved same-diagnostic retry for sandbox/network
restrictions; never dump errors, credentials, or change accounts to recover.

See [setup.md](setup.md) for human-managed remediation. In a new setup, plaintext
storage still means setup is incomplete even though the runtime check is advisory.

## Residual risks and compatibility

This trusts gh's reported source, not merely the existence of `hosts.yml`: that
file can legitimately contain non-secret account metadata alongside keyring use.
It does not search for stale tokens, duplicate copies, backups, shell startup
files, unreported accounts, or other credential stores. Environment overrides or
keyring precedence may hide old plaintext copies. PASS is limited to reported
sources; ENVIRONMENT is never proof of no plaintext on disk.

This does not verify Git's actual helper chain, repository/branch write authority,
keyring access policy, disk encryption, or isolation from same-user malware.
It cannot stop a user/agent bypassing the procedure. Trusted gh/PATH/configuration
and changes after checking remain outside the boundary. Do not use this helper
as unattended authorization or comprehensive credential discovery. No automatic
credential migration or monitoring is installed.

The metadata contract was reviewed against GitHub CLI 2.95.0. Unknown source
labels warn; malformed/unsupported output blocks, without a text-parser fallback.
Developer references (not runtime dependencies):
`https://cli.github.com/manual/gh_auth_status`,
`https://cli.github.com/manual/gh_auth_login`, and
`https://github.com/cli/cli/blob/v2.95.0/pkg/cmd/auth/status/status.go`.
