# Gitleaks engine

The adapter uses a small batch runner linked to Gitleaks 8.30.1 for Linux x86_64.
Detection rules belong to Gitleaks; framing, completion validation, the adapter,
fixed configuration, hooks, and tests are maintained here. No binary is committed
to this skill. See [runner.md](runner.md) for the pinned build and trust boundary.

This engine alone does not run the custom Python scanner. To require both,
select the [combined engine](combined.md), which uses the same pinned runner.

## Deployment boundary and locations

Skill installation copies instructions, scripts, and references; it does not
install Gitleaks or activate hooks. Docker is preferred for new Gitleaks/combined
installations. The manager copies the verified Linux x86_64 runner into the
bundle as build input and creates a local image; the scanner executes inside
that image. Explicit native mode executes the bundle binary on the host.
No daemon installation, global package, or PATH change is performed.

| Item | Location and ownership |
| --- | --- |
| Skill copy | Agent-selected directory, for example `<repo>/.agents/skills/secret-checks/`; not the runtime binary directory |
| Acquisition input | Explicit approved archive/binary staging path supplied by the caller; outside manager ownership |
| Verified runner / build input | `<git-dir>/secret-checks/bundles/<bundle-id>/bin/gitleaks-runner`; managed copy with mode `0700`, executed on the host only in native mode |
| Docker executable | `/gitleaks-runner` inside the prepared image; image storage is managed by the local Docker daemon |
| Docker image record | `<git-dir>/secret-checks/bundles/<bundle-id>/docker-image.json`; immutable local image ID |
| Active hooks | `<git-dir>/secret-checks/bundles/<bundle-id>/hooks/`; selected by repository-local `core.hooksPath` |
| State and retained versions | `<git-dir>/secret-checks/`; managed by lifecycle commands |

Resolve `<git-dir>` with `git -C /path/to/repository rev-parse --absolute-git-dir`;
do not assume it is always `<repo>/.git`. In an ordinary checkout the runtime
binary is therefore `.git/secret-checks/bundles/<bundle-id>/bin/gitleaks-runner`.
In Docker mode this host copy is retained for verified rebuilds, not executed
by the scanner. Shared-worktree configurations still require separate review.

Before setup, establish the engine, platform, acquisition input path, and target
location. Run the manager's `inspect` first. If an existing managed Gitleaks or
combined installation can supply its binary, prefer the manager's verified reuse
instead of reacquiring it. Do not run arbitrary PATH binaries to discover their
version: a version string is not verification. No acquisition or target mutation
is authorized by a request that only asks where the software is installed.

The adapter checks the binary digest and uses either a fixed local image ID or
the bundle's absolute binary path. It does not resolve Gitleaks through PATH or
depend on the acquisition directory after installation. Global upgrades cannot
silently replace the selected scanner.

Follow [docker.md](docker.md) for Docker deployment. Only the local Unix-socket
daemon is supported; Podman, remote contexts, and alternate sockets are not
automatically substituted. Docker is a separate trust boundary, not a guarantee
against host compromise. Native execution shares the hook's host account.

## Acquisition and selection

Prepare the reviewed runner using [the offline build procedure](runner.md), or
obtain the exact digest-matching artifact through an explicitly approved channel.
There is no automatic download, package installation, or build in the manager.

```sh
python3 -B scripts/manage_hooks.py install --repo /path/to/repository \
  --engine gitleaks --runtime docker --gitleaks-runner /path/to/verified/gitleaks-runner
```

Use `update` to migrate an installed bundle. Pre-batch bundles contain only
`bin/gitleaks` and cannot supply the runner: the first migration must explicitly
provide `--gitleaks-runner`. Subsequent updates reuse the active verified runner.
Runtime and engine are preserved unless explicitly changed. Rollback still
executes the retained old bundle, including its original CLI and performance limits.
The manager refuses missing/unverified runners before activation; it never falls
back to the old per-input implementation. Native mode requires an explicit choice.

### Official CLI for comparison

The official CLI is retained as an independent test oracle, not the new runtime.
Use an organization-approved acquisition process when obtaining this asset:

- Release: <https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1>
- Asset: `gitleaks_8.30.1_linux_x64.tar.gz`
- Asset SHA-256: `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`
- Extracted binary SHA-256: `88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509`

These digests preserve the migrated implementation's fixed acquisition evidence;
they are not an independent publisher signature. Verify the archive before
extracting only `gitleaks`, then verify the binary before running it. Acquisition
is an explicit setup step; neither hooks nor the manager download anything.
Use an existing approved acquisition procedure and an explicit staging location.
If none is available, report the missing binary/procedure rather than improvising
a download/install script or silently changing the requested engine. A request
to install the skill alone is not a request to acquire or execute this binary.

The optional legacy `--gitleaks` argument validates this official CLI's digest,
but does not copy it into a new bundle or satisfy the runner requirement.
Tests select it with `SECRET_CHECKS_GITLEAKS`; runtime tests select the runner
with `SECRET_CHECKS_RUNNER`. A version string is not integrity verification.

## Verification and removal

After activation, run `inspect` and `verify` through the manager. Resolve the
active bundle ID from its result, report the runtime, image ID, binary and hook paths,
and distinguish configuration, integrity, and isolated execution results.
Report acquisition-input retention separately from installed-bundle retention.
Public examples must not contain local usernames or real project paths.

`uninstall` disables the managed hooks but retains bundle binaries. `cleanup`
previews eligible versions; `cleanup --apply` removes only recorded unchanged
bundle files, including their Gitleaks copies, while protecting active/rollback
versions. Docker scan containers are removed after use; shared Docker images are
retained and their IDs are reported by cleanup. It does not remove the supplied
binary/archive, a system installation, the skill copy, or Docker images.
Acquisition files and images need separate, narrowly
scoped removal authorization; do not recursively delete a cache or temporary root.
Use the full [lifecycle procedure](installation.md) rather than manual deletion.

## Scope and limits

The adapter first applies [publication budgets and image allowances](images-and-publication.md).
Allowed image-extension blobs are not passed to the Go text detector; their names
still are. SVG passes through normal text scanning without structural parsing. The
Go protocol, binary pin and one-detector-per-hook execution are unchanged.

`pre-commit` scans every regular index blob and its path. `commit-msg` scans the
message file. `pre-push` scans the full commit/tree/blob/annotated-tag reachability
of each updated tip and destination ref metadata, including existing reachable
history. It does not trust remote-tracking refs as prior scan evidence. It parses
raw commit parent/tree links rather than relying on replace refs/grafts.

Configuration uses the fixed built-in rules. Candidate `.gitleaks.toml`,
`.gitleaksignore`, environment `GITLEAKS_*`, and inline allow comments do not alter
the adapter's policy. Built-in allowlists and Gitleaks' own detection limitations
remain. Stdin scanning cannot evaluate original path-based rule conditions merely
because path strings are also scanned.

Limits: 2 MiB per input, 32 MiB total scanner input, 1,000 objects, 64 KiB hook
stdin, 64 MiB framed transport, and 4 MiB accepted report. Git subprocesses and
Docker management calls retain their 15-second limit. Each input has a 10-second
detector deadline; the batch uses only the remaining 120-second hook budget.
Exact-container cleanup is attempted even after timeout, with its own bounded
management call. Non-UTF-8/control input other than allowed image-extension content, archives,
LFS pointers, symlinks, submodules, shallow/partial clones, missing objects and
unsupported ref namespaces cause rejection as incomplete. Large existing histories
may consistently exceed these limits; use an appropriate alternative design
rather than silently narrowing scan scope or changing engines.

The adapter captures scanner output, validates version, completion, input count,
byte count and finding identifiers, and rejects report/exit disagreements.
An empty or partial report is not a clean scan. Reports omit raw paths, refs, messages
and matched values. Exit 0/1/2 means checked/finding/error respectively.

## Receiving-side reference

The adapter retains its `pre-receive` mode for isolated tests and self-hosted Git
design exploration. Automatic installation creates only the three local hooks.
The tests build a temporary receiver hook when exercising this mode. This is not
a deployment procedure for GitHub.com, which does not accept custom receive hooks.
Receiver rejection and local pre-publication rejection provide different guarantees.
