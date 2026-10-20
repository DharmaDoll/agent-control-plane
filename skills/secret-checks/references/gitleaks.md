# Gitleaks engine

The migrated adapter supports Gitleaks 8.30.1 for Linux x86_64. Detection rules
belong to the external Gitleaks product; the adapter, fixed configuration, hooks,
and tests are maintained here. No third-party binary is committed to this skill.

## Acquisition and selection

Use an organization-approved acquisition process to obtain the official asset:

- Release: <https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1>
- Asset: `gitleaks_8.30.1_linux_x64.tar.gz`
- Asset SHA-256: `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`
- Extracted binary SHA-256: `88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509`

These digests preserve the migrated implementation's fixed acquisition evidence;
they are not an independent publisher signature. Verify the archive before
extracting only `gitleaks`, then verify the binary before running it. Acquisition
is an explicit setup step; neither hooks nor the manager download anything.

```sh
python3 -B scripts/manage_hooks.py install --repo /path/to/repository \
  --engine gitleaks --gitleaks /path/to/verified/gitleaks
```

To switch an installed Python bundle, use `update` with the same engine/binary
arguments. A normal Gitleaks update can reuse its already verified installed
binary. A different version or locally built binary is rejected, even if its
version string looks right. Adapter calls also verify the binary digest.

## Scope and limits

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

Limits inherited from the reviewed example: 2 MiB per object/message, 32 MiB total
scanner input, 1,000 objects, 64 KiB hook stdin, 15 seconds per child process,
10 seconds per scanner call, 120 seconds per hook. Non-UTF-8/control input, archives,
LFS pointers, symlinks, submodules, shallow/partial clones, missing objects and
unsupported ref namespaces cause rejection as incomplete. Large existing histories
may consistently exceed these limits; use an appropriate alternative design
rather than silently narrowing scan scope or changing engines.

The adapter captures/redacts scanner output and distinguishes findings, empty
results and invalid reports/exit codes. Its reports omit raw paths, refs, messages
and matched values. Exit 0/1/2 means checked/finding/error respectively.

## Receiving-side reference

The adapter retains its `pre-receive` mode for isolated tests and self-hosted Git
design exploration. Automatic installation creates only the three local hooks.
The tests build a temporary receiver hook when exercising this mode. This is not
a deployment procedure for GitHub.com, which does not accept custom receive hooks.
Receiver rejection and local pre-publication rejection provide different guarantees.
