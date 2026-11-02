# Sources and adaptation decisions

Reviewed on 2026-11-03. These sources explain the candidate design; they do not
certify any installed Claude Code version or demonstrate runtime enforcement.

## User-provided reference

Riotaro OKADA (`okdt`), **Claude Code Hardening Cheatsheet**, version 1.2:

- [English guide](https://github.com/okdt/claude-code-hardening-cheatsheet/blob/daf6a09568d853960a058c7cf0aef2d54361cc17/Claude_Code_Hardening_Cheat_Sheet.en.md)
- [Settings example](https://github.com/okdt/claude-code-hardening-cheatsheet/blob/daf6a09568d853960a058c7cf0aef2d54361cc17/settings_example.jsonc)
- [Audit prompt](https://github.com/okdt/claude-code-hardening-cheatsheet/blob/daf6a09568d853960a058c7cf0aef2d54361cc17/Claude_Code_Hardening_Audit_Prompt.en.md)
- [Upstream license: CC BY-SA 4.0](https://github.com/okdt/claude-code-hardening-cheatsheet/blob/daf6a09568d853960a058c7cf0aef2d54361cc17/LICENSE)

The upstream validation statement concerns Claude Code 2.1.220 on macOS. It is
not validation of this helper, other releases, or Linux. This skill uses the
reference for design review; it does not distribute its template or hook code.

| Reference idea | Adaptation here |
| --- | --- |
| Combine sandbox and tool permissions | Protect credential paths at both layers; keep their guarantees separate. |
| Inspect before changing configuration | Generate a reviewable candidate without activating it; retain existing settings. |
| Explain inconvenience, verification and recovery | Document the selected scene and return path before activation. |
| Sandbox auto-allow and common network destinations | Do not grant these conveniences by default; require human shell approval and review inherited network grants. |
| Optional startup failure and strict retry settings | Include fail-closed settings in candidates, subject to native compatibility checks. |
| Shell allow examples | Do not treat command prefixes such as `git branch *` as read-only; arguments can mutate state. |
| Custom hooks and escape logs | Do not install regex filters or whole-command logging; neither replaces process isolation, and logs can retain secrets. |
| Exceptions for incompatible commands | Do not add exclusions automatically; excluded commands lose sandbox protections. |

The audit prompt is a reference for scope and consent, not an instruction to
impose its repeated `next` interaction on the user. Existing authorization and
the requested operation determine which steps can proceed.

## Official semantics used for review

### Settings and activation

[Settings files and precedence](https://code.claude.com/docs/en/settings): managed
settings outrank command-line settings, which outrank local, project, and user
settings for ordinary scalar values. Arrays merge; an empty candidate list
does not remove existing grants. `/status` identifies loaded sources, not the
source of every effective value. Invalid entries can be skipped.

[CLI reference](https://code.claude.com/docs/en/cli-reference): `--settings`
accepts a regular JSON file up to 2 MiB or inline JSON. `--setting-sources`
selects user/project/local settings. Do not infer that changing sources removes
managed policy or all external integrations. Do not introduce `--bare`,
`--safe-mode`, or an alternate configuration home merely to pass inspection.

### Permissions and path syntax

[Permissions](https://code.claude.com/docs/en/permissions): deny precedes ask,
then allow. Use `Read(path)` and `Edit(path)` for file rules; path-scoped
`Write`, `NotebookEdit`, and `Glob` rules do not enforce file permissions.
Absolute permission paths start with `//`; a single `/` anchors to the settings
source. Read rules have best-effort coverage for some tools and do not constrain
arbitrary subprocess file access. Shell deny patterns are not syscall filters.
The same page's rule/hook/mod precedence section documents that a `tool.check`
mod can override ask/deny in personal sessions without managed settings or an
active Team/Enterprise login. Review these mods before relying on the candidate.

### Sandbox boundary

[Sandboxing](https://code.claude.com/docs/en/sandboxing): the built-in sandbox
covers shell commands and their descendants. File/web tools, hooks, MCP, LSP,
and helper commands are separate surfaces. The sandbox supports macOS, Linux,
and WSL2; native Windows is outside this candidate design. Temporary-directory
writes are part of the default boundary. Commands typed through `!` generally
run outside it and are unsuitable evidence that sandbox restrictions work.

[Settings reference](https://code.claude.com/docs/en/settings-reference):
`failIfUnavailable` prevents startup fallback; `allowUnsandboxedCommands: false`
prevents the model's unsandboxed retry. `strictAllowlist` requires 2.1.219 or
later. An empty `allowedDomains` alone does not prohibit connections: permission
mode and inherited `WebFetch(domain:...)` grants matter. Custom proxy settings
replace built-in filtering. Sandbox filesystem paths use ordinary absolute
paths, and wildcard behavior varies by platform. Check `filesystem.disabled`,
excluded commands, socket access, and weakening flags before activation.

## Evidence boundary

Current documentation includes behavior introduced after the cheatsheet's
tested version. A version string, JSON parsing, or a unit test of this helper
does not prove Claude Code accepts or enforces its candidate. Keep candidate
integrity, native settings acceptance, effective source review, synthetic
sandbox probes, and interactive approval behavior as separate evidence.

Recheck these sources when promoting a recipe. Never treat a documentation
minimum version as proof that every later release is compatible.
