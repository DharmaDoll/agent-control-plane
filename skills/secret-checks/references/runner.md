# Gitleaks batch runner

## Purpose and boundary

Issue #7 showed that starting Gitleaks separately for every path and object can
consume the 120-second hook budget on benign repositories. A process pool still
repeats detector initialization; concatenating inputs can change allowlists,
multiline matching and chunk boundaries. The runner initializes the detector once
and scans independent inputs. Git enumeration and policy validation stay in Python.

For a step-by-step explanation of the hook path, Go detector calls, input
isolation, and completion checks, see [gitleaks-hook-flow.md](gitleaks-hook-flow.md).
This reference remains the source for build pins and the protocol contract.

One hook uses one runner process, or one hardened Docker container. Inputs travel
through memory/stdin only: no host payload files, mounts, image layers, network,
shell, or resident service. The runner uses the upstream stdin fragmenter with the
existing fixed text header, empty detector file paths, default rules, ignored
allow comments, and disabled decoding/archive traversal. No repository config,
baseline or ignore file is loaded. The reviewed policy file's SHA-256 is checked
before loading defaults. Rule changes require a reviewed rebuild, not a target
repository override.

## Reproducible build and acquisition

Build inputs are `runner/main.go`, `runner/go.mod`, and `runner/go.sum`.
Toolchain: Go **1.26.8**, Linux/amd64, `CGO_ENABLED=0`, `GOAMD64=v1`.
Upstream detector: **v8.30.1**. `-tags=gore2regex` matches the official CLI's
regex engine. Builds use `-mod=readonly -trimpath -buildvcs=false` and
`-ldflags='-s -w -buildid='`. The reviewed artifact SHA-256 is:

```text
13483d25dc5c1f110b35e8f70aca21e0fa6aec1783d4fc406d2ea186d005982e
```

Obtain the exact toolchain and checksum-verified module cache through an approved
acquisition process first. Missing prerequisites are a blocker, not permission
for hooks or the manager to fetch software. Then, from the skill directory:

```sh
python3 -B scripts/build_runner.py \
  --go /approved/go1.26.8/bin/go \
  --module-cache /approved/go/pkg/mod \
  --output /approved/artifacts/gitleaks-runner
```

The output must not exist. The helper disables proxy/toolchain downloads,
workspace files and ambient Go settings, verifies the module cache, builds in a
private temporary directory, and publishes only a digest-matching artifact.
It does not change hash pins, install hooks, or delete the supplied toolchain/cache.
Build staging is removed; the output remains caller-owned. Do not accept an
arbitrary supplied hash or relax verification to accommodate a different build.

Supply this artifact as `--gitleaks-runner` to `install` or `update`.
Go is needed only on the build machine, never during hooks or normal installation
of a prepared artifact. Source/library/toolchain provenance and digest review
remain trusted; a reproducible hash is not an independent signature or audit.
Gitleaks and its dependencies retain their upstream licenses; include required
notices when redistributing compiled artifacts.

## Internal protocol (version 1)

The entire stream is bounded to 64 MiB. Integers are unsigned big-endian:

```text
"SCB1" | input-count:u32 | original-byte-count:u64
        | sequence:u32 | length:u32 | original-bytes[length]  (repeated)
EOF
```

Sequence numbers start at zero; lengths are checked before allocation. Each
input is UTF-8 text with the control restrictions, the
[standalone LFS header policy](limitations.md#lfs-pointer-recognition), and 2 MiB limit;
the total original bytes cannot exceed 32 MiB. Missing, reordered, extra or
truncated frames, byte-count disagreement and trailing bytes refuse the scan.
Empty batches and empty inputs still require a complete validated response.

Output is a single JSON object: `version:1`, `complete:true`, `processed`, `bytes`,
and `findings:[{input, rules:[rule-id,...]}]`. Only rule IDs and numeric indexes
are emitted, never source data, filenames or detailed upstream errors. Findings
are collected per input; detector state does not retain findings between inputs.
Read errors and expired contexts fail closed instead of using upstream's
log-and-continue source wrapper. Exit codes are 0 (complete/clean), 10
(complete/findings), and 2 (incomplete). The adapter maps findings to hook exit 1;
all incomplete or inconsistent results to hook exit 2.

## Residual risks and unsuitable uses

The new Go program, pinned libraries and build toolchain add a maintenance and
review boundary. Upstream built-in allowlists, unknown secrets and chunking
limitations still apply. Comparing fixtures to the CLI is not proof of universal
equivalence. Memory remains observable to a trusted host/daemon; no secure-erasure,
OS-level native memory isolation, or protection from a malicious local user is
claimed. Go's 160 MiB memory target is soft; Docker keeps its hard 256 MiB limit.

Do not use this design for unsupported platforms, non-text input, workloads
outside the fixed limits, or policies requiring original-path-aware rules.
Do not expand limits or fall back to another engine after a refusal.
