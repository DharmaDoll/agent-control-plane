# Compatibility maintenance

## Stable intent, small version adapters

[recipes.json](../compatibility/recipes.json) holds exact tested versions,
OS/architecture, handler IDs, required CLI capabilities and references. It is
reviewed distribution data, never downloaded at runtime. It cannot contain
commands or executable expressions. The manager implements a finite set of
renderer/probe handlers and rejects unknown schema/handler IDs.

The initial Linux x86_64 recipe targets Codex 0.163.0 and permission profiles.
Its review profile extends `:read-only`; development adds workspace writes while
keeping `.git`, `.agents`, `.codex` and `.aws` read-only. General temporary paths
are not writable. Both disable command networking, select on-request approvals
with a human reviewer and disallow login shells. Read access is not confined to
the workspace: this is not a secret-file confidentiality boundary.

An exact version match alone never establishes readiness. The native executable
identity and required help markers are checked, and apply must pass synthetic
probes. Unknown versions remain inspectable but cannot be applied. Same-version
replacement invalidates the plan fingerprint. No broad `>=` version promises.

## Initial conservative configuration boundary

The helper checks the user config, system and home managed-config locations,
every workspace ancestor's `.codex/config.toml`/hooks/rules and user hook/rule
files. It does not infer project trust or reproduce Codex's entire config resolver.
Existing project/managed layers, hook/rule files, security-model settings, feature
flags, telemetry or unrecognized top-level keys block automatic application.
This conservative superset can block a layer Codex would ignore; that is a
review request, not an invitation to remove it. Presence-only MCP/history/log
observations are not certification of those surfaces.

Handling those combinations later requires bounded, tested adapters. Do not add
an `--ignore-unknown` escape hatch. Broadening supported config is a code change
with tests, not a runtime agent interpretation or a web-derived rule injection.

## Updating support

1. Obtain the requested release through an independently approved process. This
   skill never upgrades/downgrades Codex or changes credentials automatically.
2. Review official release notes, version-matched source/schema when available,
   current docs and local CLI help. Record provenance, revision/digest and date
   in validation evidence. Schema validity does not prove runtime enforcement.
3. Run existing fixtures and real probes against the trusted native binary. A
   failure may be an interface change, behavior regression or host limitation;
   classify it before editing settings.
4. Reuse a handler when behavior is unchanged. If not, add the smallest explicit
   handler and reproducer. Preserve the stable intent tests.
5. Re-run every version/OS still advertised as tested. Record unavailable binaries
   as NOT RUN; do not claim mocked versions are runtime-certified.
6. Add the exact tested version to a recipe only after evidence. Distribute the
   reviewed skill update. At each deployment, re-run inspect/plan/apply/verify.

Fingerprint inputs include executable bytes/path, related configuration files,
profile/state, compatibility definition, script, Python identity, OS, UID and
workspace/home. Verification is never cached; it rechecks before and after
probes and rejects drift. No continuous monitor or mandatory launch wrapper is
installed. A caller that does not run this manager is not stopped by it.

## References and observed differences

- [Official configuration layering](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [Official permission profiles](https://learn.chatgpt.com/docs/permissions)
- [Official approval/sandbox guidance](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Official execution rules](https://learn.chatgpt.com/docs/agent-configuration/rules)

The installed 0.163.0 sandbox CLI requires `--permission-profile` when selecting
a config profile and rejects `--strict-config` for `sandbox`. Real initial
tests exposed both cases; neither was treated as a successful policy denial.
Use actual handler tests instead of assuming every global CLI flag is supported
by every subcommand. Consult validation evidence for the tested binary digest.
