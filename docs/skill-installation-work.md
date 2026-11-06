# Work item: simple, verifiable skill distribution

## Goal and agreed scope

Implement the user's final, simplified design: acquire one fixed Git commit in
an explicitly permitted workspace directory, copy selected skills without
overwriting existing directories, and detect incomplete installation. Partial
failure is acceptable; silent or unverifiable success is not.

Latest user refinement: after successful installation, retain only the installed
skills. The expected-content JSON now belongs in the permitted acquisition
directory and is removed together with the helper/source by the documented
success cleanup. Failed/interrupted work may remain and must be reported.
Later verification requires the source SHA from the final report and a fresh
acquisition; without that record, exact original-version attribution is lost.

The common helper is an offline Python 3.10+ standard-library script with only
`install` and `verify`. It reads immutable Git objects from an explicitly named
local checkout of this repository. It creates no system temporary files, runs no
skill code, changes no authentication or agent settings, and installs no resident
manager. There is no journal, snapshot, automatic rollback, update engine, or
privilege escalation. Installed skills remain self-contained.

The GitHub acquisition procedure uses Git in a new directory beneath an
explicitly permitted work directory. It resolves a ref once, extracts the helper
from that commit, and uses that exact commit for every selected skill. Cleanup is
limited to that newly created acquisition directory; a failure leaves its path
visible. Both agent destinations are independent operations.

## Acceptance criteria

| ID | Required behavior | Evidence |
| --- | --- | --- |
| AC1 | All five named skills, or an explicit subset, can be copied to either agent's standard skills directory. | Isolated CLI fixtures for both destinations and a real-repository snapshot. |
| AC2 | A full commit SHA and matching helper identify source bytes; uncommitted changes do not enter the payload. | Modified-worktree and helper-mismatch tests. |
| AC3 | Before any skill copy, one expected-content JSON is saved in an explicitly allowed work directory outside the skill directories. Successful cleanup removes auxiliary files. | Failure injection, interrupted-process and cleanup checks. |
| AC4 | Existing skill directories/files/links are never overwritten or completed implicitly. | Existing, partial, symlink and repeat-run cases. |
| AC5 | Missing, modified, extra, unsafe, or unreadable content is never reported as matching. | File/mode/directory boundary tests and nonzero CLI status. |
| AC6 | After partial failure or interruption, verify derives each skill's state from files and the saved manifest, without the source checkout. | Interrupted copy and offline verification. |
| AC7 | No /tmp dependency, network operation, skill-code execution, active configuration changes, or permanent helper cache occurs in the helper. | Workspace-only fixtures, subprocess review, documented side effects. |
| AC8 | README provides an all-five prompt, host/scope choices, fixed acquisition, exact verification and partial-failure guidance. | Documentation review and local rehearsal of the command sequence. |

## Interface baseline

```text
manage_skills.py install --source <absolute-checkout> --commit <full-SHA>
  --dest <absolute-.agents/skills-or-.claude/skills>
  --manifest <permitted-work-directory>/skills-install[-label].json
  (--all | --skill <name> [--skill <name> ...])
manage_skills.py verify --manifest <absolute-manifest>
```

The expected manifest contains repository, commit, helper SHA-256, destination,
selected skill names and per-file relative path, SHA-256, size and executable bit.
It has no mutable success flag. An identical existing manifest can be reused;
a different or invalid existing manifest is not overwritten. Existing skills are
skipped and still verified. Exit zero requires every selected skill to match and
no copy error. Reports distinguish the copy action from the observed file state.

Inputs, manifest schema and paths are bounded and validated. Selected source
symlinks, gitlinks and unsupported modes are rejected before destination writes.
Destination and verification paths are opened without following symlinks.
The helper cannot prevent an uncooperative same-user process from moving open
directories; concurrent installation/editing is outside the guarantee.

## Tasks and dependencies

| Task | Depends on | Completion condition | Status |
| --- | --- | --- | --- |
| T1: Record agreed design and CLI | None | Scope and observable acceptance criteria fixed | Complete |
| T2: Implement offline install/verify | T1 | Bounded source/manifest/filesystem behavior | Complete |
| T3: Isolated contract tests | T1 | Normal, collision, corruption, interruption and permission cases | Complete |
| T4: Rewrite installation documentation | T1 | Shared recipe and all-five UX, no obsolete manager design | Complete |
| T5: Independent review and workflow rehearsal | T2, T3, T4 | Findings resolved and actual final artifacts verified | Complete |

## Initial state and validation limits

Base HEAD observed: b0b85f8 (Claude installation documentation).
Existing untracked `skills_plan/` and concurrent controlled-github authentication
work are unrelated and must be preserved. README edits are limited to the
installation sections, preserving other concurrent additions.

This is a new helper, so there is no executable pre-change helper baseline.
Tests will use synthetic repositories, ordinary files, and local process failure
injection. No active user skill installation or native agent session is part of
automated validation. Linux is the available execution environment; other OS and
native discovery results must remain explicitly unverified unless exercised.

## Execution record

Executed on 2026-11-04, Linux, Python 3.10.4, Git 2.47.2.

### Automated contract checks

```sh
python3 -B -m unittest discover -s tests -p 'test_manage_skills.py' -v
```

44 tests passed in the final run (10.544 seconds), with no skips. The tests create
all fixtures beneath this workspace, use synthetic Git identities and local
repositories, and clean up
their fixtures. Coverage includes both hosts and subset selection; source/helper
pinning; existing files, partial trees and links; manifest write failure; actual
abrupt child-process exit; independent verification after source removal;
modified/missing/extra files and executable bits; unsafe special files;
destination/manifest denial; strict JSON/path handling; an external temporary
manifest, its unchanged reuse and successful acquisition-directory cleanup;
and a real local Git promisor repository with a missing blob. The
temporary-directory check uses fresh
Python children with an audit hook rejecting tempfile APIs and accesses beneath
/tmp and /var/tmp. Negative controls prove that these denials are active before
install and verify run. This covers the helper interpreter, not Git's internal
filesystem syscalls; the local Git object-read commands were reviewed separately.

### Independent review and actual workflow rehearsal

The independent reviewer reproduced two bugs before correction: lazy Git object
fetching from partial clones, and treating a FileExistsError after copying as a
successful existing-directory skip. The corrected helper disables all Git
transports for its subprocesses and distinguishes initial mkdir collisions from
copy failures. Both reproductions now stop/report correctly and are covered by
regression tests. Post-manifest directory/stat errors also preserve per-skill
verification output. No further material finding remained in that review.

An earlier workflow rehearsal used all five real skill directories (76 files per
host) and confirmed their contents, hashes and executable bits. It also checked
that the unrelated-path cleanup guard refused removal and preserved a sentinel.
That rehearsal preceded the final temporary-manifest policy.

After the user's refinement, the independent reviewer executed the current
documentation's actual Bash acquisition, installation and cleanup blocks against
a workspace-local Git mirror. Only the acquisition transport was substituted
using a fixture-local URL rewrite; this was not a GitHub live test. Both agent
destinations received the same commit and all five synthetic skill fixtures
(15 files per host), with distinct manifests inside the acquisition directory.
Successful cleanup left only the skills, with no source, helper or manifest.

Re-acquiring the recorded full SHA and repeating both installations produced
SKIPPED_EXISTING/MATCH for every skill. File hashes, inodes and modification times
were unchanged, and cleanup succeeded again. A preexisting edited skill instead
produced exit 1/INCOMPLETE, preserving its contents and the acquisition directory
and manifest. This later same-version operation is a new installation attempt:
fully absent directories could be created. Only verify with an existing manifest
is read-only. No further material code or documentation finding remained.

### Security choices and validation limits

CodeGuard guidance was applied to strict inputs, no-follow/exclusive filesystem
operations, JSON parsing, SHA-256 integrity checks, and subprocess argument
arrays. No secrets are embedded/read, no shell is invoked by the helper, and no
TLS/certificate configuration is implemented or changed. The Git commit SHA is
an existing Git identifier, not a new cryptographic authentication mechanism.

Native agent discovery/compliance, GitHub live acquisition, macOS and Windows
execution were not run. Byte matching does not establish native runtime safety
or publisher authenticity. Neither active user skill directories nor the root
repository's Git metadata were changed by these tests. Unrelated concurrent
controlled-github work and draft files remain outside this change's validation.

### Artifact fingerprints

```text
scripts/manage_skills.py
6e55001ba2d2c09b95fa52a80e1c687559ef2bdf3f080b8566a526b986fc7edb

tests/test_manage_skills.py
6d49dbca122dee7a41fea58d99bc1724c68076449656ff73d71db859b6ba9d77
```

Documentation links, Bash block syntax and patch whitespace were checked. Only
this validation record was updated after the final command-sequence rehearsal.

## Completion audit

| Criteria | Final evidence | Result |
| --- | --- | --- |
| AC1 | Both-host/all-five and subset contract tests; earlier real-skill rehearsal and current both-host Bash rehearsal | PASS |
| AC2 | Pinned old commit with dirty/newer worktree; helper mismatch rejection; SHA-based reacquisition | PASS |
| AC3 | Manifest interruption prevents copying; abrupt exit leaves readable record; current Bash cleanup leaves only skills | PASS |
| AC4 | Existing partial directory/file/symlink and identical rerun tests; no overwrite flag or deletion code | PASS |
| AC5 | Missing/content/extra/executable-bit, hardlink/symlink/FIFO/unreadable, strict schema and traversal cases | PASS |
| AC6 | Actual child os._exit followed by fresh-process verify after source deletion; local Git lazy-fetch regression | PASS |
| AC7 | System-temp denial with negative controls, child-only transport restrictions, copied script sentinel, destination inventory | PASS within documented local-process boundary |
| AC8 | README all-five prompt/host-scope options; local Bash rehearsal including cleanup and reacquisition; local links and original anchors checked | PASS |

Implementation is complete in the working tree. Publishing these new files to
GitHub is a separate operation; a public commit without the helper cannot run the
new acquisition recipe. Native discovery and live GitHub checks remain NOT RUN,
as specified above, rather than being inferred from local fixture success.
