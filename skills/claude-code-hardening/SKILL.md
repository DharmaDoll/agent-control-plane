---
name: claude-code-hardening
description: Review Claude Code CLI hardening and generate reproducible review or development settings candidates, with explicit activation checks and recovery. Use for hardening setup, configuration review, or revalidation after an update; not ordinary coding, automatic upgrades, or organizational policy deployment.
---

# Claude Code hardening

Prepare a bounded local-tool policy for Claude Code. This skill is self-contained
and can be invoked as `/claude-code-hardening` in Claude Code. Its Python 3.10+
helper uses only the standard library on POSIX systems.

**Current evidence: candidate generation and artifact checks only. No Claude Code
version is runtime-certified.** The helper neither starts Claude nor changes its
active settings. Do not describe a generated candidate as installed, active,
offline, or sandbox-verified. Read [operations.md](references/operations.md)
for exact commands and the activation gate.

## Inspect before changing anything

Establish the requested operation, workspace, OS home, actual Claude config
directory, trusted executable and exact CLI version. Never substitute another
home to bypass a conflict. Inspect only relevant setting names and classifications;
do not dump config bodies, environment values, MCP URLs, credentials or logs.

Account for user, project, local, command-line and managed settings, environment
overrides, hooks, plugins, MCP and additional directories. Use the existing
session's `/status`, `/permissions` and `/sandbox` views where available. Report
unknown sources as `REVIEW_REQUIRED`; do not infer defaults or remove controls.
An inspection request authorizes no export, activation, probes, cleanup or upgrade.

Read [sources.md](references/sources.md) when interpreting settings or updating
compatibility. Third-party templates are design references, not authority to run
their hooks or overwrite settings. Settings lists merge; an empty list does not
remove inherited permissions, sandbox exclusions, network grants or write paths.

## Choose a scene and prepare the candidate

- `review`: file-tool investigation with editing, shell execution and delegation
  denied. This intentionally does not offer shell-based review or test execution.
- `development`: manual approval for shell commands and file edits, with sandbox
  controls and credential-path denies. Builds may fail when they need network,
  protected metadata, credentials or unsupported host services.

Use the scene already requested. If none is clear, explain these two choices
and establish which the user needs. Read
[limitations.md](references/limitations.md) before proposing activation or exceptions.

Run `plan` with [scripts/harden.py](scripts/harden.py). Review the generated
settings, output destination and plan ID. A plan does not inspect effective
settings or establish compatibility. Export the accepted plan to a new private
candidate file outside the workspace. Existing authorization to create that
candidate is sufficient; ask only for missing authority or a material scope change.
The helper does not merge into any `settings.json` and never overwrites a file.

Preserve default protections. If an exception is necessary, explain its impact
and obtain authorization for the named scope. This initial helper has no opt-out
or arbitrary-settings switch; do not hand-edit its output and call it verified.
Treat a custom policy as separate compatibility work, with separate evidence.

## Verify, activate and report separately

`verify` checks candidate bytes against the generator. `ARTIFACT_MATCH` means
only that; runtime enforcement remains `NOT_VERIFIED`. Changed inputs, helper
or file bytes require a fresh plan and a new output path.

Only proceed to activation when the user has authorized it and the version,
effective sources and isolation checks in operations.md can be established.
Stop when a required key is unsupported, silently ignored, overridden, or unknown.
Do not install dependencies, upgrade Claude, change authentication, disable
existing hooks or retry outside the sandbox to make verification pass.

Use a new session with the reviewed `--settings` candidate only after that review.
The initial session is a validation session with synthetic data, not permission
to work on sensitive data. Do not launch it automatically. A shell `!` command
does not test Claude's sandboxed tool execution.

Report the candidate path, scene, exact version, artifact result, unresolved
settings layers, and native tests actually run. Keep static checks, agent
evaluations and live enforcement results separate; see
[validation.md](evals/validation.md). Native Windows and WSL1 are outside scope.

## Recovery

Stop the candidate session and omit its `--settings` argument on the next launch
to return to the previous configuration. This restores the previous selection,
not a security guarantee. Keep previous candidate files for comparison; use a
new filename for each revision. Delete only an explicitly selected inactive
artifact when cleanup is requested. There is no automatic history purge or
modification of authentication, MCP, project configuration or managed policy.
