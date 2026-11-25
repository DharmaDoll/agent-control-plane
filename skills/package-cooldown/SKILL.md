---
name: package-cooldown
description: Inspect installed package managers and configure minimum package release ages for a user. Show the exact settings, project overrides, verification and undo instructions before and after applying a cooldown.
---

# Package release cooldown

Use this workflow on POSIX development machines. The starting policy is seven days, or the positive integer day count requested by the user. A cooldown gives registries and maintainers time to detect and remove compromised releases. It can also postpone security fixes. Locked versions, direct URLs and private indexes can have different coverage. Never test enforcement by downloading a package during this workflow.

## Inspect (default)

1. Record the project directory and the requested user account. Run `python3 scripts/inventory.py` from the skill directory to list executable paths without launching any clients. Locate npm, pnpm, yarn, bun, pip (including the selected interpreter's pip), uv, gem, bundle, cargo, composer and go on PATH. Show missing clients. A manifest or a Corepack shim alone does not prove a client is installed. Use only trusted installed executables. Disable shim downloads and project plugins or inspect their files statically. If this cannot be done safely, report the client as unverified.
2. Use [the client recipes](references/clients.md) to establish version, support for a **relative** duration, actual user file, user value, project-effective value and source. Run version/help probes from a neutral directory. Inspect project configuration as data. Use only trusted projects for commands that load executable configuration. Check environment overrides by name and targeted lookup. Never print configuration dumps, raw errors from parsers, unrelated settings or credentials. Display only valid duration values, disabled status and exception presence/count. Redact unexpected values.
3. Show a row per client with executable/version, affected operation, absolute file, key, current user value, proposed value with units, expected effective value in this project and its source. Include configured exclusions and relevant defaults. Use explicit states for missing, unsupported, existing, proposed, and unknown. A query that returns no value for an unknown option does not establish support.
4. Propose an addition only when the user setting is absent and the applicable user default is below target. Preserve explicit settings including zero, shorter periods and exceptions; report any shortfall. A known project override can coexist with a new user default: show both. Skip writes when the effective sources, capability or destination cannot be established. Go is inventory-only until a verified native recipe exists.

## Apply and verify

Present the preview to the user before writing. Apply only when setup is requested, using the reviewed scope. Recheck the target and prerequisites immediately before each write. If the preview changed, present the new plan first. Use the fixed recipes below with integer-derived values, in a trusted user-owned directory, without concurrent editors, symlinks, elevated privileges or redirected paths outside the user's home. Do not install or update clients. Process shared configuration one client at a time and reinspect after each change.

For each client report the pre-change value, exact path/key, stored value read back, project-effective value with source, and a precise undo action. For a newly added key, undo means removing just that key from the same file after checking its current value. Preserve other changes. If verification fails, distinguish “written, effective value unverified” from “write failed”; re-inspect before retrying. A file readback verifies storage only. Report inferred effective values as inferred and identify the configuration sources used. Live package resolution is outside this check.

Example report for npm (illustrative paths):

| Stage | User setting | Project result |
| --- | --- | --- |
| Before | /home/dev/.npmrc, min-release-age, absent → 7 days | /work/app/.npmrc explicitly selects 3 days; expected 3 days |
| After | /home/dev/.npmrc, min-release-age = 7 days, read back | npm config get min-release-age in /work/app returned 3 days |
| Undo | Remove only min-release-age from /home/dev/.npmrc | The project's 3-day setting is independent |
