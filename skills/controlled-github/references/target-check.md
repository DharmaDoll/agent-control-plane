# Local target check

Run from any directory, substituting independently approved expectations:

```sh
python3 <skill-dir>/scripts/check_target.py \
  --root <expected-worktree-root> --remote <remote-name> \
  --host <expected-host> --repo <owner/repository> --transport <https-or-ssh>
```

Python 3.10+ and Git are the only runtime dependencies. The helper performs no
network calls, credential lookup, index updates, ref changes, or config writes.
It calls Git with argument arrays, no shell, captured output, and a 10-second
timeout per subprocess. Run it in the same environment as subsequent Git commands.

It checks the canonical worktree root (including linked worktrees), configured
URL count, effective fetch and push URLs after Git's `insteadOf`/`pushInsteadOf`
rewrites, and mirror configuration. Both effective targets must match the expected
host, owner/repo, and transport. A trailing `.git` is optional; host comparison is
case-insensitive, repository comparison deliberately case-sensitive.

Supported forms:

```text
https://github.com/owner/repository.git
ssh://git@github.com/owner/repository.git
git@github.com:owner/repository.git
```

Equivalent fetch/push spelling is accepted, but multiple URLs, differing targets
or transports, mirror mode, HTTPS userinfo, SSH passwords, control characters,
queries/fragments, percent-encoded paths, explicit ports, local paths, custom
remote helpers, and other protocols are blocked. SSH aliases are not resolved:
an alias differing from the expected hostname fails the target comparison.
Do not use an alias as the expected host to pretend the actual destination was
verified. Custom ports and aliases require a separately reviewed mechanism.

Git repository/index/config injection environment overrides (`GIT_DIR`,
`GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`, `GIT_CONFIG`,
`GIT_CONFIG_COUNT`, `GIT_CONFIG_PARAMETERS`) are blocked, not silently removed.
Trusted global/system config paths are still honored, so effective URL rewrites
are checked. This is not an audit of every Git setting or of the environment.

## Output contract

One JSON object on stdout; no raw URL or Git stderr is forwarded. Exit 0 means
PASS; exit 2 means BLOCKED. `--help` prints usage and exits 0, not a target PASS.
Only a successful result includes the validated target:

```json
{"status":"PASS","reason":"LOCAL_TARGET_MATCH","target":{"host":"github.com","repo":"owner/repo","transport":"https"}}
```

Failures contain only `status` and a fixed `reason`:

| Reason | Meaning / next check |
| --- | --- |
| `INVALID_ARGUMENTS` | Missing or unsupported CLI arguments. |
| `ROOT_MISMATCH` | Given directory is not the actual worktree root. |
| `TARGET_MISMATCH` | Effective destination differs from the approved target. |
| `FETCH_PUSH_MISMATCH` | Effective fetch and push destinations differ. |
| `MULTIPLE_OR_MISSING_URLS` | Cannot establish exactly one destination per direction. |
| `MIRROR_REMOTE` | Mirror mode is enabled or ambiguous. |
| `EMBEDDED_CREDENTIALS` | URL contains forbidden userinfo/password; human remediation needed. |
| `UNSUPPORTED_URL`, `UNSUPPORTED_REPOSITORY` | Outside the accepted syntax. |
| `GIT_ENV_OVERRIDE` | Explicit Git routing/config override is present. |
| `GIT_CHECK_FAILED` | Git could not complete a local check, e.g. missing remote or invalid config. |
| `GIT_TIMEOUT` | A local Git subprocess exceeded its timeout. |
| `CHECK_UNAVAILABLE` | Path, executable, decoding, or parsing check could not complete. |

A BLOCKED result deliberately omits sensitive detail. Do not work around it by
printing full Git config or raw remote URLs. A human can inspect private config
outside the agent context when the reason alone is insufficient.

PASS is **not** authentication, authorization, network reachability, branch policy,
or code validation. It does not resolve SSH configuration, DNS, HTTP redirects,
proxies, hooks, credential helpers, or concurrent configuration changes. Trust
the execution environment and recheck immediately before network writes.
