# Validation record

Date: 2026-11-03. Target: initial uncommitted Claude Code candidate-generator
implementation, on Linux with Python 3.10.4. No native Claude executable was
found on PATH. No dependencies or Claude installation were added.

## Automated checks: PASS

```sh
python3 -B -m unittest discover -s skills/claude-code-hardening/evals -p 'test_*.py' -v
```

34 tests passed using temporary local fixtures. Coverage includes both scenes,
read-only deterministic planning, plan invalidation after input/source/directory
changes, private export, exact-byte verification, tamper detection, no overwrite,
publication races, failed-publication cleanup, protected paths, symlinks, hardlinks,
FIFOs, oversized/public files, unsafe output parents, and sanitized CLI errors.
Candidate-policy assertions are generator tests, not native denial tests.

Tested source fingerprints (SHA-256):

```text
scripts/harden.py
5302196de103cec7416862a5a819ee6c967d57d161f1edcd19894be0b50dbf5f
evals/test_harden.py
2e7e44e2f6e7c34aca4fcf48ceac06edda8b9a68cc9a7f348485d4a744e77444
```

The skill-creator frontmatter/scaffold validator passed. Local Markdown reference
targets and patch whitespace were checked. This validator is a development tool,
not a distributed runtime dependency.

## Independent agent evaluation: bounded PASS

A separate agent read the skill and exercised the actual CLI using isolated
`/tmp` fixtures for both scenes. Observed: plans created no files and had stable
IDs; export produced mode 0600; verify returned `ARTIFACT_MATCH` with
`runtime: NOT_VERIFIED`; overwrite, tampering and symlink cases were refused.
The agent also ran the 34 unit tests successfully.

Review identified ambiguity in bare Edit ask coverage and plugin-mod permission
overrides. The final candidate explicitly asks for Write/NotebookEdit as well,
and the activation gate documents `tool.check` overrides. Final automated tests
were rerun after the code change. No real settings, credentials or services were
used. This is not a Claude Code agent-behavior evaluation.

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
