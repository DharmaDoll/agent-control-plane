# Scope, trust boundary, and limits

## Problem and mechanism

A secret may be staged even when the worktree looks clean, or remain in an older
commit after being removed from the latest tree. A final-tree-only scan can miss
that publication. Standard Git hooks invoke reviewed, deterministic scanners
before commit/push and reject findings or incomplete scans. The agent chooses the
requested management operation; scripts determine installation and refusal.

The implementation is canonical in this skill. It was migrated from
`DharmaDoll/product-security-guidance` at commit
`2b5e81df0eee973d4cc4fc493fe09d93d207ea0b`, under
`engineering/source-protection/secret-checks-before-publication/implementations/`.
The upstream pattern explains architectural alternatives; this skill owns the
maintained scanner code, hooks, configuration, and executable tests.

## Python engine

Both engines now apply [static-image rules and publication budgets](images-and-publication.md).
Validated raster contents are not secret-scanned; SVG remains text-scanned.
The text-only restrictions below apply to all other input.

- Uses Python's standard library and the inherited example's 12 explicit secret
  patterns plus sensitive filename policy. It does not claim Gitleaks-equivalent
  coverage. Environment templates are name-allowed but still content-scanned.
- `pre-commit` scans added/changed/renamed index blobs, not the worktree. It rejects
  unresolved index entries, symlinks and submodules. Unchanged existing index blobs
  are not rescanned for content in this mode.
- `commit-msg` scans the message file supplied by Git.
- `pre-push` uses Git's actual update OIDs. For an existing destination, it scans
  introduced commits; for a new destination, all commits reachable from that tip.
  Commit messages and changed blobs are scanned; merges use each parent's diff.
  Explicit commit-SHA sources are accepted when the destination is a branch.
  Deletions introduce no commits; all other updates in the invocation are checked.
- Tags and non-branch destinations, shallow/partial clones, missing objects,
  symlinks, submodules, NUL input, and detected LFS pointers are unsupported and
  stop the operation. Some archive/binary names are refused by filename policy;
  archives are not unpacked. Non-NUL binary/encoded data is not comprehensively
  recognized or decoded. Use a different reviewed design if those formats matter.
- Replacement refs are disabled. There is no certificate validation, network
  credential validity check, entropy engine, baseline, inline bypass, or user
  exception facility.
- Limits: 5 MiB per input, 32 MiB scanned bytes, 1,000 scanned items or introduced
  commits, 64 KiB hook stdin, 30 seconds per Git subprocess, 120 seconds per hook.
  Captured Git metadata is checked after retrieval; this is not an OS memory sandbox.
  Validated raster bytes use the separate image budget, not the text-byte budget.
- Output includes rule IDs and hashed location IDs; matched values and raw paths
  are suppressed. Ref metadata findings also omit the ref value.

Scanner exit 0 means no findings in the configured scope; 1 means findings; 2 means
ERROR/incomplete. Git itself may map a failing hook to a different nonzero exit.

## Gitleaks engine

See [gitleaks.md](gitleaks.md). It scans full reachable objects and supports tags,
but deliberately rejects many formats and large histories. Its limits and detection
behavior are different; never substitute one engine for another after a failure.

[Docker runtime](docker.md) is preferred for new Gitleaks/combined installations.
It isolates the detector, not the host Git enumeration or custom Python policy.
Container startup counts toward hook deadlines. The Docker daemon and prepared
image are additional trusted components; Docker failure never selects native
execution. Shared images remain after bundle cleanup.

## LFS pointer recognition

All three validation layers (Python scanner, Gitleaks adapter, and batch runner)
refuse a standalone `version` line naming the current Git LFS v1 URL or either
legacy URL (`hawser.github.com` and `git-media.io`). This follows the version
identifiers in the [Git LFS pointer implementation](https://github.com/git-lfs/git-lfs/blob/main/lfs/pointer.go)
and the [pointer specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md).
Leading/trailing whitespace, CRLF, missing fields, and malformed remaining fields
do not turn recognized pointer-like metadata into a clean scan. No LFS content is
downloaded. Empty inputs remain ordinary empty content.

A version string embedded in a quoted source literal or inline prose is not a
pointer. That content continues through all normal secret checks; it is not an
allowlist. This is conservative header recognition, not a full pointer parser:
standalone version lines in fenced documentation examples also refuse the scan.
Use a separately reviewed design when inspecting actual external LFS objects is
required; this control cannot establish the safety of those objects.

## Trust and residual risks

The [combined engine](combined.md) requires both scanners on push. By default it
runs only Python on pre-commit and commit-msg; Gitleaks can be enabled there with
`--commit-gitleaks on`. Python misses can enter local history before push detects
them. Commit image/publication checks remain enabled. This schedule does not
guarantee that local commits are free of Gitleaks-only findings.
It inherits both sets of restrictions, including Python's refusal of tag pushes
and Gitleaks' stricter content budget. It improves coverage but shares the same
local trust boundary and cannot guarantee absence of secrets.

The local OS account, installed interpreter, Git, shell, Git configuration,
reviewed skill copy, hook bundle and its management record are trusted. Per-file
hashes identify content drift, not authenticity against that same account.
Concurrent malicious edits and a compromised runtime are outside the mechanism.
The manager serializes its own writes but does not lock all possible Git editors.

The scanned index/ref OIDs identify the intended inputs, but local concurrent
changes can invalidate assumptions. Git hooks are bypassable and cloning does
not install them. GitHub push protection, required merge checks, Web/API/bot
writes, LFS servers and external submodule contents need separate controls.
Rejection by a receiver does not mean its server never received the bytes.

Do not use this as unattended enforcement against the machine's owner, as a full
repository audit, or as evidence that all credentials are absent. False positives
and missed/unknown secret formats remain possible. Actual exposure requires
credential revocation and investigation even when later scans pass.
