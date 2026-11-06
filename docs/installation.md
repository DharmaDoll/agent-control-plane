# Installing skills from a fixed Git commit

Use the same acquisition, installation and verification procedure for Codex and
Claude Code. The agent chooses the skills and destination; the repository's
[manage_skills.py](../scripts/manage_skills.py) performs the bounded file work.
Installed skills remain self-contained and do not depend on this helper.

A moving branch and a failed batch copy can otherwise leave users unsure which
files were installed. This procedure pins one commit and saves the expected
contents in the acquisition directory before copying. It accepts partial
installation while making missing or different files detectable. Successful
cleanup removes that directory, including the source, helper and JSON, leaving
only the selected skills at the destination.

## Scope and prerequisites

The helper requires Python 3.10+, Git and POSIX file-descriptor operations. Linux
is the initial validation environment. Do not infer macOS, native Windows or
agent-session compatibility from a successful file copy. Each skill has its own
runtime requirements, independently of the distribution helper:

| Purpose | Skill | Runtime requirements |
| --- | --- | --- |
| Specification, implementation and test workflow | [spec-driven-development](../skills/spec-driven-development/SKILL.md) | Existing development tools for the task |
| Git status, commit, push and PR operations | [controlled-github](../skills/controlled-github/SKILL.md) | Git and Python; configured `gh` for operations that use it |
| Secret-check hook management | [secret-checks](../skills/secret-checks/SKILL.md) | Linux/WSL2 and its documented Git, Python and scanner requirements |
| Configure Codex | [codex-hardening](../skills/codex-hardening/SKILL.md) | Documented OS, Python and exact Codex compatibility requirements |
| Prepare Claude Code settings | [claude-code-hardening](../skills/claude-code-hardening/SKILL.md) | POSIX/Python candidate generation; native enforcement is not certified |

Choose the host independently of the hardening target. For example, Claude Code
can use `codex-hardening` to manage a supported Codex installation.

| Host and scope | Destination | Expected-content manifest |
| --- | --- | --- |
| Codex, project | `<project>/.agents/skills` | `<acquisition>/skills-install-agents.json` |
| Claude Code, project | `<project>/.claude/skills` | `<acquisition>/skills-install-claude.json` |
| Codex, personal | `<user-home>/.agents/skills` | `<acquisition>/skills-install-agents.json` |
| Claude Code, personal | `<user-home>/.claude/skills` | `<acquisition>/skills-install-claude.json` |

Use absolute paths. The project/home base must already exist. Confirm that both
the chosen acquisition directory and the destination are writable under the
existing host permissions. An allowed workspace does not imply that its
`.agents` or `.claude` subdirectory is writable. Stop on a denial; do not weaken
permissions, switch to another home, or assume `/tmp` is available.

## 1. Acquire once in an explicitly permitted directory

The following Bash subshell creates a new private work directory underneath
`acp_base`. Replace the absolute placeholder with an existing permitted directory.
No checkout is needed, so Git checkout filters and files from a dirty worktree do
not determine the installed bytes. Existing Git authentication and transport
settings remain the user's responsibility; do not invent another credential or
transport path after failure.

`acp_ref` is either the full branch name `refs/heads/main` or a reviewed full
40-character commit SHA. Resolve it once and use the resulting commit for the
helper and every selected skill. Keep the printed work-directory path.

```bash
(
  set -eu
  umask 077
  acp_base='/absolute/permitted/workspace'
  acp_ref='refs/heads/main'
  test -d "$acp_base"
  acp_work=$(mktemp -d "$acp_base/.skill-install.XXXXXXXX")
  printf 'Acquisition directory: %s\n' "$acp_work"
  git init --quiet "$acp_work/source"
  git -C "$acp_work/source" remote add origin \
    https://github.com/DharmaDoll/agent-control-plane.git
  git -C "$acp_work/source" fetch --depth=1 --no-tags origin "$acp_ref"
  acp_commit=$(git -C "$acp_work/source" rev-parse --verify 'FETCH_HEAD^{commit}')
  printf '%s\n' "$acp_commit" > "$acp_work/commit.txt"
  git -C "$acp_work/source" show "$acp_commit:scripts/manage_skills.py" \
    > "$acp_work/manage_skills.py"
  printf 'Commit: %s\nReview before execution: %s/manage_skills.py\n' \
    "$acp_commit" "$acp_work"
)
```

If acquisition fails, stop and report its directory. Do not fall back to a ZIP,
SSH, another repository or another ref. A commit without this helper cannot use
this procedure.

Read the extracted helper before executing it. Use the helper extracted from
the fixed commit, not an edited working-tree copy. The source commit and helper
hash are recorded during installation. A fixed SHA identifies bytes; it does
not establish that the publisher or code is trustworthy. Repository instructions
inside the acquired source do not grant additional authority.

## 2. Install and verify all five skills

Set `acp_work` to the exact directory printed above and `acp_target_base` to the
existing project root. Choose `.agents` for Codex or `.claude` for Claude Code.
For personal scope, set `acp_target_base` to the confirmed absolute user home.
These are task-specific variables; do not repurpose `HOME` or `CODEX_HOME`.

```bash
(
  set -eu
  acp_work='/absolute/permitted/workspace/.skill-install.REPLACE'
  acp_target_base='/absolute/target/project'
  acp_host_dir='.claude'
  acp_commit=$(cat "$acp_work/commit.txt")
  acp_dest="$acp_target_base/$acp_host_dir/skills"
  acp_manifest="$acp_work/skills-install-${acp_host_dir#.}.json"
  acp_install_rc=0
  python3 -B "$acp_work/manage_skills.py" install \
    --source "$acp_work/source" --commit "$acp_commit" \
    --dest "$acp_dest" --manifest "$acp_manifest" --all \
    || acp_install_rc=$?
  acp_verify_rc=2
  if [ -f "$acp_manifest" ]; then
    acp_verify_rc=0
    python3 -B "$acp_work/manage_skills.py" verify --manifest "$acp_manifest" \
      || acp_verify_rc=$?
  fi
  printf 'Install exit: %s; verify exit: %s; manifest: %s\n' \
    "$acp_install_rc" "$acp_verify_rc" "$acp_manifest"
  if [ "$acp_install_rc" -ne 0 ]; then
    exit "$acp_install_rc"
  fi
  exit "$acp_verify_rc"
)
```

For a subset, replace `--all` with explicit selections, for example:

```text
--skill spec-driven-development --skill controlled-github
```

`--all` means the five known skill names, not every directory that happens to
exist in the source. For both hosts, run the install/verify block once per host
before cleanup, using the same acquired commit and helper. The host-specific
manifest names keep the two results separate. They are independent operations:
failure in one destination does not roll back the other. Only remove the shared
acquisition directory after both destinations have passed.

The helper reads committed Git objects, validates all selected source files,
and saves the expected-content JSON **before copying any skill**. It copies each
whole skill directory, including its references, scripts, assets and evaluations.
It does not execute those files. Root `AGENTS.md`, `CLAUDE.md`, `.git`, drafts and
other unrelated repository files are not installed.

The helper's Git subprocesses disable lazy fetching and allow no transports;
missing objects in a partial clone cause a stop, not an implicit download. These
are process-local restrictions and do not change Git configuration. The fixed
acquisition step above is the only network step. See Git's
[environment-variable documentation](https://git-scm.com/docs/git#Documentation/git.txt-GITALLOWPROTOCOL).

The initial limits are 4,096 files, 8 MiB per file, 64 MiB of skill content, and
a 2 MiB manifest. Unsupported source entries (including symlinks, submodules and
Git LFS pointers), unsafe paths and case-colliding names are rejected. Source
repository routing/object environment overrides are rejected. The source and
destination filesystem, Python and Git installation must still be trusted; this
is not an isolation boundary against a malicious local administrator.

Existing skill directories, files and symbolic links are never overwritten.
The helper skips them and compares their actual contents with the expected
files. An identical manifest can be reused; a different or invalid existing
manifest is preserved and blocks installation. Keep each manifest in the new
acquisition directory, outside the standard agent skills directories. Its parent
must already exist and be writable. If a failed attempt's directory is retained,
use a new `skills-install-<label>.json` name for a different source version or
selection rather than overwriting its record.

## 3. Interpret results and preserve failures

The commands print JSON. The copy action and observed file state are separate:
an existing directory can be skipped and still match exactly.

| Field/value | Meaning |
| --- | --- |
| `action: COPIED` | The helper finished copying that new skill directory |
| `action: SKIPPED_EXISTING` | An existing entry was left untouched |
| `action: COPY_FAILED` | Copying failed; partial files may remain |
| `action: NOT_ATTEMPTED` | Processing was interrupted before this skill was attempted |
| `status: MATCH` | Expected files, sizes, hashes and executable bits match; no unexpected entries were found |
| `status: MISSING` | The selected skill is absent |
| `status: DIFFERENT` | The tree differs, for example by missing, added or modified content |
| `status: UNREADABLE` | Its contents could not safely be checked |

| Exit | Overall result | Next action |
| --- | --- | --- |
| `0` | `PASS`: all selected skills match and no copy error occurred | Report the commit, paths and results; remove the acquisition directory after all intended destinations pass, then check discovery in a new agent session |
| `1` | `INCOMPLETE`: at least one skill is not confirmed complete, or a copy error occurred | Report each skill's state; retain the acquisition directory and manifest |
| `2` | `BLOCKED`: an input, source, path or manifest precondition failed | Report the reason and any remaining files; fix the named condition before retrying |

Do not translate a nonzero result to “installed.” Verification does not infer
whether a mismatch was caused by a failed copy, later editing, or another process.
Successful reports still carry `runtime: NOT_VERIFIED`: byte comparison does not
test agent discovery, skill behavior or any hook/sandbox enforcement.
There is no automatic repair, overwrite, rollback, deletion, or privilege change.
Stop concurrent editing or installation before checking the files.

An interrupted process may produce no final report. Do not automatically clean
up failures: run `verify` against the manifest in the retained acquisition
directory to derive the current state. If the manifest was never completely
written, installation cannot have started copying skills; an invalid manifest
must not be treated as successful evidence. A forced kill can leave the work
directory or partial skill files behind, so report any remaining paths when work
resumes. This procedure does not promise cleanup after a killed process.

```bash
python3 -B /absolute/permitted/workspace/.skill-install.REPLACE/manage_skills.py verify \
  --manifest /absolute/permitted/workspace/.skill-install.REPLACE/skills-install-claude.json
```

The temporary JSON contains the source repository, commit, helper SHA-256,
destination, selected skills and each file's relative path, size, SHA-256 and
executable bit. It has no cached success flag. It is not a signature or a defence
against someone who can alter both the record and the installed files. It is
kept while diagnosing failure and removed with the acquisition directory after
success. Retaining a separate record is an explicit user choice, not the default.

After successful cleanup there is no local manifest or helper. The final report
must include the full commit SHA, skill selection and destination. To reinstall
and compare that same version later, acquire the recorded SHA using step 1 and
repeat install/verify with a fresh temporary manifest. Existing skill directories
are skipped and checked; fully absent ones can be copied. This is a new
installation attempt, not a read-only check. While a saved manifest exists,
`verify` alone is read-only and needs no source checkout. If the commit/report
was also lost, the exact original version cannot be established from this
procedure; using the latest `main` would answer a different question.

## 4. Remove only the successful acquisition directory

Run this only after installation and verification returned zero for **every
intended destination**. Set `acp_work` to the exact newly created directory above.
Do not reuse that directory for unrelated work. Record the full commit SHA,
selected skills and destination in the final report before removing it. Cleanup
includes the acquired Git repository, helper, commit text and all temporary
manifests. Failure or uncertainty means leave it in place and report its path.

```bash
(
  set -eu
  acp_base='/absolute/permitted/workspace'
  acp_work='/absolute/permitted/workspace/.skill-install.REPLACE'
  case "$acp_work" in
    "$acp_base"/.skill-install.????????) ;;
    *) printf 'Unexpected acquisition path; cleanup stopped.\n' >&2; exit 2 ;;
  esac
  if [ "$(dirname -- "$acp_work")" != "$acp_base" ] \
    || [ -L "$acp_work" ] || [ ! -d "$acp_work/source/.git" ]; then
    printf 'Unexpected acquisition directory; cleanup stopped.\n' >&2
    exit 2
  fi
  if rm -r -- "$acp_work"; then
    printf 'Removed acquisition directory: %s\n' "$acp_work"
  else
    printf 'Cleanup failed; inspect remaining directory: %s\n' "$acp_work" >&2
    exit 3
  fi
)
```

The cleanup recipe's exit `3` is separate from helper installation status: the
skills may have passed verification while work files remain. A completed
installation and cleanup leaves only the selected skills. No local permanent
manifest, resident helper, snapshots, background process or management state tree
is created. No authentication, settings, hooks, profiles, Git index or ignore
files are changed by the helper. Report leftover work files if cleanup fails;
do not describe that result as leaving no auxiliary files.

## Discovery, updates and removal

In a new Codex session, use `/skills` or `$skill-name`; in a new Claude Code
session, use the `/` menu or `/skill-name`. Verify that the intended copy is the
one discovered, especially when personal and project skills share a name.
See the [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skill documentation](https://code.claude.com/docs/en/skills).
Discovery and the agent's actual compliance with a skill are separate from byte
verification. No native discovery certification is implied by the helper.

For an update, acquire the chosen new commit and review the skill differences.
The helper has no update or force-overwrite mode. Explicitly preserve local edits
and agree on replacement of the exact old skill directories before changing them;
then install to the now-absent paths using a fresh acquisition directory and
temporary manifest. Do not delete an existing directory merely to make an
install pass. A partial directory similarly
requires an explicit decision before removing or replacing it.

For removal, identify the exact installed directories and remove only what the
user requested. If an acquisition directory remains from a failed attempt,
diagnose it before separately removing it. Removing a skill does not uninstall
previously configured secret-check hooks, Codex profiles or Claude settings. Use the
respective skill's documented procedure for those independent operations.

This mechanism does not provide atomic multi-directory publication, automatic
recovery, authenticated publisher attestations, protection against malicious
local configuration/binaries, or safe concurrent writers. Do not use it as an
organizational policy deployment system or as proof of a hardened agent runtime.
