# Installation and lifecycle

All examples run the script from a reviewed copy of this skill. Replace the
repository argument with the exact worktree root. No credentials or network are
needed for the Python engine or lifecycle probes.

## Inspect, install, verify

```sh
python3 -B scripts/manage_hooks.py inspect --repo /path/to/repository
python3 -B scripts/manage_hooks.py install --repo /path/to/repository
python3 -B scripts/manage_hooks.py verify --repo /path/to/repository
```

The initial default is the Python engine. `inspect` is read-only. Management
returns JSON: exit 0 means the requested operation completed; exit 2 means
BLOCKED. An inspection PASS means diagnosis completed, not that checks are
installed or that the recommendation has been executed.

Inspection includes index-entry/unsupported-mode counts and Git object-database
counts/sizes (Git reports storage sizes in KiB). These are inventory evidence,
not a full content scan or a prediction that all history fits an engine's limits.
Known unsupported index modes route to `REVIEW_INDEX`; clone limitations route
to `REVIEW_CLONE`. File formats and scanner budgets remain subject to the actual
scanner's fail-closed checks.

The automatic installer supports single-worktree, fully materialized Linux Git
repositories with no `core.hooksPath` at any scope and no non-sample default hooks.
It rejects ambiguous Git-routing environment overrides. It accepts an existing
installation only when its record, effective setting, and files agree. It does
not modify global/system configuration, authentication, or repository content.

The manager resolves the Git administration directory through Git rather than
assuming `.git` is a directory. It stores:

```text
<git-dir>/secret-checks/
├── state.json
├── lock
└── bundles/<content-digest>/
    ├── scripts/<selected-scanner>.py  # Combined: dispatcher and both scanners
    ├── hooks/{pre-commit,commit-msg,pre-push}
    └── bin/gitleaks + gitleaks.toml    # Gitleaks or combined engine
```

The bundle ID covers the engine, generated hooks, scanner, configuration, binary
when applicable, and executable modes. Hooks pin the current Python executable
by absolute path and use isolated Python mode and `/usr/bin/git`. Moving/removing
that interpreter requires an update from a reviewed environment. A bundle is
independent of the skill's original location and is not automatically updated
when the skill checkout changes. Digests detect drift; they are not publisher
signatures or protection against the local account changing code and records.

To require both scanners, use the [combined engine procedure](combined.md).
Its binary must be verified before activation; existing installations are not
automatically migrated.

The manager records expected contents before copying, verifies a candidate with
real local Git operations, then sets the local `core.hooksPath`. It reads back
the setting before recording activation. If preparation fails, the old hook
configuration remains in place. A process lock serializes cooperating managers.
Do not run configuration editors or other managers concurrently.

## Existing hooks and worktrees

`REVIEW_EXISTING_HOOKS` means preserve the existing installation and inspect its
owner's documented integration interface. Propose the exact call and order:

- `pre-commit`: both checks must succeed; propagate failures.
- `commit-msg`: pass Git's message-file argument unchanged.
- `pre-push`: both consumers need the full original stdin. Running one consumer
  and piping the depleted stream to another is incorrect.

Review and test that integration separately in a fixture before configuring the
target. This manager does not provide a generic hook-chain generator or claim
that a manually integrated configuration passed its managed-install verification.

`REVIEW_WORKTREES` means multiple worktrees share settings, or the requested root
is a linked worktree. Report the affected roots and decide a shared or per-worktree
configuration before integrating. The first automatic installer refuses writes
in this situation; it does not silently enable worktree-specific configuration.

## Update and rollback

```sh
python3 -B scripts/manage_hooks.py update --repo /path/to/repository
python3 -B scripts/manage_hooks.py rollback --repo /path/to/repository
```

Run `update` from the reviewed new skill version. It preserves the selected engine
unless `--engine` explicitly selects another. Repeating installation of the same
bundle is idempotent; use `update` when the payload differs. An unchanged result
checks file integrity but does not rerun the probes; use `verify` to rerun them.
The previous active version is retained. `rollback` rechecks and probes that
version before activating it and keeps the other version as the new previous.

Preparation or probe failure leaves a recorded inactive candidate. Preview
cleanup to remove that candidate if its files are still unchanged. A partially
written file that does not match the record is retained for manual review.

## Uninstall and cleanup

```sh
python3 -B scripts/manage_hooks.py uninstall --repo /path/to/repository
python3 -B scripts/manage_hooks.py cleanup --repo /path/to/repository
python3 -B scripts/manage_hooks.py cleanup --repo /path/to/repository --apply
```

Uninstall removes the local hook setting only if it is still the expected managed
value. The original automatically supported state is no hook setting; the manager
does not adopt or overwrite an existing external setting. Bundle files are retained
until cleanup. Repeating uninstall or cleanup is safe.

Cleanup previews by default. While installed, the active and immediately previous
bundles are protected. After uninstall, all recorded inactive bundles are eligible.
Each candidate must contain only expected directories and regular files, with
matching digests and modes. Recorded incomplete bundles may contain a subset of
the expected files. Unknown/modified content and symlinks are retained and reported;
untracked entries are not named in output because names may contain secrets.

Deletion uses explicit file unlink operations followed by empty-directory removal.
There is no recursive delete of unchecked paths, no scan of the user's home or
temporary directories, and no deletion of worktree files, default hooks, or external
scanners. A minimal `state.json`, empty bundles directory, and process lock remain
for auditability and safe repeated management. Deleted bundle files can be rebuilt
from their reviewed source version; removed private local modifications cannot be
recovered by this tool and are therefore never automatically deleted.

## Recovery and reporting

If the effective setting changes, management stops with
`HOOK_CONFIGURATION_CHANGED`; do not overwrite the new setting. If a crash occurs
between a Git config write and state recording, inspection reports a mismatch.
Compare the record and Git's scoped configuration manually, restore the known
previous value or complete the reviewed activation, and rerun inspect/verify.
Do not mark an interrupted activation as complete.

Reports contain fixed reason codes and managed bundle IDs, not secret values,
foreign hook contents, raw scanner stderr, or arbitrary filenames. `verify`
confirms the target's effective configuration and bundle bytes; executable probes
run against that same bundle in isolated repositories. No commit is made in the
target to prove live target invocation, and no SaaS acceptance behavior is tested.
