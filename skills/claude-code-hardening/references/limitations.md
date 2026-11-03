# Policy boundaries and defaults

## Problem and trust boundary

An agent can accidentally expose credentials, destroy local changes or approve
commands with excessive scope. A prose instruction alone does not enforce a
boundary. Generating a new settings mechanism ad hoc for every session also
makes the intended policy difficult to review or reproduce.

This skill generates fixed settings from explicit paths and a selected sample.
Its plan ID binds the candidate and inputs; export refuses overwrites, and verify checks
the expected bytes. The Python helper is trusted local code, not a sandbox.
Its filesystem safeguards do not defend against a malicious process running as
the same user or an administrator. Keep candidates and their parent directories
under the operator's control, outside agent-writable workspaces.

Claude Code's tool permission evaluator and OS sandbox enforce different
boundaries. File tools need Read/Edit rules; arbitrary shell subprocesses need
sandbox filesystem rules. Neither contains the whole Claude process. The
operator, OS administrator and managed policy remain trusted. Review their
configuration before activation, as described in [operations.md](operations.md).
Plugin mods handling `tool.check` can override ask/deny decisions in some
personal sessions; the activation gate must rule out that interaction. Rules
alone do not establish the claimed prompt or denial behavior in such a session.

## Default intent

All samples request manual permissions, disable bypass and auto permission modes,
deny WebFetch/WebSearch and delegation, and enable sandboxing with no automatic
shell approval or unsandboxed fallback. Development asks before shell commands
and editing. Review additionally denies command tools and all editing; it is a
file-tool review scene, not a read-only shell sandbox.

The review/local-development samples add no network grants. The two dependency
samples add only their declared public-registry hosts; none adds extra-write
grants. Host access is not download-only access or a package safety check.
Strict allowlisting is requested, but inherited domain grants can survive.
Existing write paths, excluded commands and sockets also need review.
An empty array is not a revocation.
The sandbox normally permits its temporary directory; this is not Codex's profile
with general temporary-directory writes withheld. Local binding and socket
restrictions depend on platform and optional runtime dependencies.

Credential paths are denied to file tools and sandboxed subprocesses. The
catalogue covers default SSH, cloud, Kubernetes, container-registry, Terraform,
Pulumi, Vault, GitHub/GitLab, Git, npm/PyPI/Cargo/Ruby, netrc, GnuPG and database
stores below the explicit OS home, plus default Claude credential/config files.
The helper constructs these names without opening or enumerating the stores.
Blocking them can prevent authenticated CLIs from working.

Workspace `.env` is denied at both boundaries. `.env.*` variants are covered by
file-tool rules only; do not assume Linux sandbox glob support protects every
variant. Move secrets outside the workspace or add separately reviewed concrete
paths before allowing subprocesses to handle such a project. Metadata denies
cover workspace `.git` and `.claude`; linked-worktree metadata and other
repositories require separate inspection.

No protection is inferred for custom XDG paths, `CLAUDE_CONFIG_DIR`, external
service-account files, environment credentials, sockets, keyrings, open file
descriptors, hardlink aliases or mounted alternate paths. Secret management
belongs outside the model. Do not dump environment/configuration to diagnose
authentication; never copy secrets to bypass a deny.

## Command rules and other execution paths

Selected sudo/su forms are denied and development shell calls require human
review. These are tool decisions, not syscall filters. An interpreter can delete
workspace files, another binary can implement privilege escalation, and a remote
service can change state without Git. Human approval, ordinary OS privileges,
server-side branch protection and backups still matter. No regex hook can
certify all shell syntax; this skill does not install one.

Hooks, MCP servers, plugins, LSP, status commands, API-key helpers and operator
shell commands can run outside the sandbox. Existing security hooks are preserved,
not disabled merely to simplify the candidate. Claude's API traffic, transcripts,
telemetry and retention policy are not changed. Do not claim this policy prevents
all exfiltration, prompt injection, data loss or a compromised host.

## When not to use this candidate

- Native Windows, WSL1 or an unverified sandbox implementation.
- Organizational enforcement: use administrator-controlled policy with its own
  deployment and validation, not an optional local candidate file.
- Work requiring unreviewed hooks/MCP, socket access, custom proxies, additional
  network grants, inherited exclusions, or credentials denied by this catalogue.
- Untrusted projects requiring whole-process containment: put the entire agent
  and its services in a separately managed container or VM first.
- A promise of native protection without the exact-version activation checks.

Do not weaken protections automatically on failure. Record the blocked capability
and design a named, authorized exception separately. The current generator has
no exception flag and does not replace the existing Codex hardening manager.
