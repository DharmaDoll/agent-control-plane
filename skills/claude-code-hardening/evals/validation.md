# Validation record

Date: 2026-11-03. Target: scenario-selection update to the Claude Code
candidate generator, on Linux with Python 3.10.4. No dependencies or Claude
installation were added. The initial implementation found no native Claude
executable on PATH; native enforcement remains untested in this update.

## Automated checks: PASS

```sh
python3 -B -m unittest discover -s skills/claude-code-hardening/evals -p 'test_*.py' -v
```

43 tests passed using temporary local fixtures (34 baseline plus 9 selector
tests). Coverage includes all four samples,
read-only deterministic planning, plan invalidation after input/source/directory
changes, private export, exact-byte verification, tamper detection, no overwrite,
publication races, failed-publication cleanup, protected paths, symlinks, hardlinks,
FIFOs, oversized/public files, unsafe output parents, and sanitized CLI errors.
The new tests cover catalogue listing without file access, explicit domain-only
changes, all sample lifecycles, legacy setting-byte compatibility, canonical
aliases, stale plans on sample changes, cross-sample verification refusal and
invalid/ambiguous CLI arguments. Candidate-policy assertions are generator tests,
not native denial tests. No package downloads or installation were tested.

Tested source fingerprints (SHA-256):

```text
scripts/harden.py
5cd57967176533ff34a1749a14a523a3afccf9966c1429fe3b7d5e458f22dfa2
evals/test_harden.py
8711f0148e2d1430621511434139769ee86711fe2f8a50099493c28ca3565b06
```

The skill-creator frontmatter/scaffold validator passed. Local Markdown reference
targets and patch whitespace were checked. This validator is a development tool,
not a distributed runtime dependency.

## Initial independent agent evaluation: bounded PASS

A separate agent read the initial skill and exercised the actual CLI using isolated
`/tmp` fixtures for both scenes. Observed: plans created no files and had stable
IDs; export produced mode 0600; verify returned `ARTIFACT_MATCH` with
`runtime: NOT_VERIFIED`; overwrite, tampering and symlink cases were refused.
The agent also ran the 34 unit tests successfully.

Review identified ambiguity in bare Edit ask coverage and plugin-mod permission
overrides. The final candidate explicitly asks for Write/NotebookEdit as well,
and the activation gate documents `tool.check` overrides. Final automated tests
were rerun after the code change. No real settings, credentials or services were
used. This is not a Claude Code agent-behavior evaluation.

## Scenario-selection forward evaluation: bounded PASS

A separate agent received four realistic requests and the skill, without the
expected sample choices. It exercised the actual CLI in isolated `/tmp` fixtures:

| Request | Observed choice and result |
| --- | --- |
| Python bug fix with dependencies already installed | `local-development`; no added domains; plan created no files. |
| Source reading without execution or editing | `code-review`; shell/edit denies present; plan created no files. |
| Public npm dependency retrieval before tests | `npm-dependencies`; only the registry host added; export/verify succeeded with 0600 and `ARTIFACT_MATCH`. |
| Unattended production cloud deployment | No matching sample recommended; separate design required, no candidate generated. |

Runtime stayed `NOT_VERIFIED`. The npm candidate retained manual approval and
home `.npmrc` protection. No repository edits, native Claude invocation, package
installation, real-config inspection or network operations were part of this
evaluation. Successful package retrieval and native enforcement remain untested.

## Native and live checks: NOT RUN

- Claude Code parsing of the candidate on any exact version.
- Effective source resolution, managed settings and environment overrides.
- Actual Read/Edit rules, shell sandbox filesystem/network enforcement, sockets,
  exclusion handling and unsupported-sandbox fallback.
- Human approval UI, subagents, mods, hooks, MCP, IDE and plugin interactions.
- macOS/WSL2 execution, credential integrations and real-service operations.

There is no certified version recipe and no automatic activation command.
`--claude-version` binds an operator label into a plan; it does not discover,
approve or test a binary. `ARTIFACT_MATCH` is never sandbox PASS. Follow the
[native activation gate](../references/operations.md#native-activation-gate)
before claiming protection in a real session.
