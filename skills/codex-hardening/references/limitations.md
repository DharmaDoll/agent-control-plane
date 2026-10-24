# Security boundary and limitations

## Problem and mechanism

Agent instructions alone cannot enforce machine permissions. Blindly copying a
config template is also unsafe when settings disappear, change semantics or are
overridden by another layer. This skill manages two small version-specific
profiles using explicit targets, deterministic checks, synthetic probes,
fingerprinted plans, bounded/redacted diagnostics and recoverable file updates.
Codex/OS sandboxing provides enforcement; this skill does not implement a sandbox.

## Trust and residual risk

- The operator, local account, trusted native Codex/Python binaries, distributed
  skill files and OS remain trusted. SHA-256 detects changes, not malicious code
  or authenticity. An attacker with the same account can alter both records and
  profiles. This is not a privileged multi-user service.
- Filesystem checks, single-writer locking and pre/post fingerprints address
  accidental drift and cooperative concurrency, not hostile same-UID races.
  Uncooperative editors must not edit managed paths during an operation.
- The profiles retain broad read access. They do not prevent reading local
  credentials into model context. Keep secrets out of accessible workspaces or
  use independently enforced read boundaries and external credential brokers.
- Writes inside a development workspace can change executable code, scripts and
  dependency hooks. Narrow writable roots do not make all allowed writes safe.
- On-request does not prompt for every command. Existing permits, CLI overrides,
  approved escalations and later session changes can change behavior. The current
  automatic workflow blocks existing rule files rather than certify them.
- Shell/network sandboxing is not a global communications policy. Web search,
  MCP/connectors, browser/computer tools, model API traffic and telemetry have
  separate paths. The loopback test and disabled network setting do not prove
  zero exfiltration or prevention of every protocol/tunnel.
- MCP configuration is observed, not activated/tested or rewritten. No remote
  tool, account or external service is contacted. Auth storage changes require
  their own review; no token value is read or migrated.
- History, session state, memories and logs are separate retention surfaces.
  `history.persistence = "none"` is not a promise that nothing remains. This
  manager only reports selected config observations and never deletes history.
- Temporary probe writes and controlled subprocess environment differ from a
  live model session. Approval UI and environment filtering are NOT RUN, even
  when local-command sandbox checks PASS. Activation needs a new session using
  the reviewed installation, home, workspace and profile without overrides.
- macOS, Windows, managed enterprise settings, other architectures, unreviewed
  CLI versions and additional agent products are not automatically supported.
  WSL2 needs its own host probes; Linux compatibility alone is not a WSL2 pass.

Do not use this as unattended privileged automation, blanket DLP, a substitute
for OS isolation or an enterprise policy enforcement system. Unknown conditions
stop application rather than silently weaken configuration.

## Source acknowledgement

The motivation includes okdt's
[Codex CLI Hardening Cheatsheet](https://github.com/okdt/codex-cli-hardening-cheatsheet)
and its
[Japanese guide](https://github.com/okdt/codex-cli-hardening-cheatsheet/blob/main/Codex_CLI_Hardening_Cheat_Sheet.ja.md).
That project identifies its license as CC BY-SA 4.0. No guide text or template
is vendored here; this implementation and procedures were written for this
repository using official documentation and local runtime evidence. Review
licensing/attribution separately before copying upstream material in the future.
