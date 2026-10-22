# Gitleaks hook execution and Go runner

The current adapter also enforces [publication budgets and image validation](images-and-publication.md).
Validated raster content is counted as allowed but unscanned and is not framed
for the Go text runner. SVG still enters text scanning. The execution path below
describes the remaining text inputs; the Go protocol and detector are unchanged.

The Gitleaks engine runs a purpose-built Go binary linked to the Gitleaks
detection library. It does not launch the official Gitleaks CLI for each input.
Python selects and validates the Git inputs; Go initializes one detector, scans
each input independently, and returns a completion report. Git, not an agent or
LLM, acts on the hook's exit status.

This walkthrough describes the batch implementation with Docker and the combined
engine. It does not imply that hooks are enabled in a particular repository.
Installation and lifecycle commands remain in [installation.md](installation.md);
the pinned build and protocol contract remain in [runner.md](runner.md).

## Hook execution flow

The two-engine path below applies to push and to explicitly enabled commit
Gitleaks checks. New combined installations run only Python on pre-commit and
commit-msg by default, reporting an explicit Gitleaks skip. See
[the schedule and opt-in setting](combined.md).

The repository-local `core.hooksPath` selects a versioned bundle's hooks.
The generated hook invokes the bundled Python dispatcher with the appropriate
mode and Git arguments:

```text
Git launches a hook
  |
  v
combined_gate.py                              Host
  |
  +-- 1. scan_sensitive.py
  |      Run the custom Python scanner
  |
  +-- 2. gitleaks_gate.py
         Enumerate Git inputs and validate their format and size
         Queue independent inputs and serialize one batch
         |
         | stdin with explicit input boundaries
         v
       One Docker container
         |
         v
       gitleaks-runner                        Go
         Initialize one Gitleaks detector
         Scan inputs sequentially and independently
         Return completion metadata and finding rule IDs
         |
         v
       Python validates container state
       Remove the exact scan container
       Validate the JSON report and exit status
  |
  v
Continue Git only when both engines succeed
```

[combined_gate.py](../scripts/combined_gate.py) runs Python first, then Gitleaks,
even if the first engine reports a finding or error. Invalid dispatcher arguments
or unreadable hook input can stop execution before either engine starts.
For `pre-push`, the dispatcher reads stdin once and replays identical bytes to
both engines. It suppresses child diagnostics and reports only each engine's
status. See [combined.md](combined.md) for the combined policy.

One container means one per hook, not one per Git command. A normal successful
commit runs `pre-commit` and `commit-msg`, each with its own container. `pre-push`
is separate. Unsupported inputs can be refused before a container is started.
The Gitleaks-only engine omits the custom scanner but still uses the Python
adapter. Explicit native mode runs the same Go binary without Docker.

## Why batching improves execution

Previously, every path or content input required another container or process
and another detector initialization. This startup overhead could exhaust the
hook deadline on benign repositories. For example, 500 files with distinct blob
contents produce approximately 1,000 inputs when names and contents are separate.

The batch implementation creates one container and one detector for all those
inputs. It is startup reuse, not parallel scanning or a resident worker service.
It does not concatenate unrelated contents into one detection input, which
could change multiline matching, allowlist behavior, and fragment boundaries.

In [gitleaks_gate.py](../scripts/gitleaks_gate.py), `Scanner.scan()` validates and
queues bytes; it does not immediately invoke Gitleaks. `Scanner.finish()` frames
the queued inputs and performs the single invocation.

The Gitleaks adapter retains its inspection scope:

- `pre-commit` scans the paths and contents of all regular index files, not only
  changed files. Identical blob objects are inspected once, while their paths
  remain separate inputs.
- `commit-msg` scans the prepared message file.
- `pre-push` walks the full reachable history of updated tips, including existing
  reachable history, and scans destination ref metadata. Commit and annotated-tag
  contents are inspected along with file contents and tree entry names.

The index, not the worktree, supplies commit content. The Go runner does not
invoke Git or explore the repository. See [gitleaks.md](gitleaks.md#scope-and-limits)
for the exact scope and supported input types.

## The Go wrapper and detector initialization

[runner/main.go](../runner/main.go) directly imports the upstream `detect` and
`sources` packages. The pinned Gitleaks library is compiled into `gitleaks-runner`;
there is no runtime `exec.Command("gitleaks", ...)` call. The official CLI remains
an independent test oracle, not a runtime dependency.

`execute()` validates its arguments and the supplied policy file's SHA-256,
then initializes the detector once. The relevant settings are:

```go
detector, err := detect.NewDetectorDefaultConfig()
// Initialization errors abort the scan.
detector.IgnoreGitleaksAllow, detector.Redact = true, 100
detector.MaxDecodeDepth, detector.MaxArchiveDepth = 0, 0
```

The detector uses upstream built-in default rules. Inline `gitleaks:allow`
comments cannot exempt inputs, redaction is enabled, and automatic decoding and
archive traversal are disabled. Built-in upstream allowlists still apply.

The `--config` argument is not an arbitrary configuration interface. The runner
checks the file against the reviewed policy digest, then loads compiled defaults;
it does not parse that file as a user-supplied TOML configuration. Repository
configuration, ignore files, baselines, and ambient Gitleaks environment settings
do not override this policy. Changing it requires a reviewed code/build update.

## Input framing and validation

Python sends the `SCB1` binary protocol defined in
[runner.md](runner.md#internal-protocol-version-1). Its header declares the input
count and total original byte count. Each frame carries a zero-based sequence
number, byte length, and that input's bytes. All integers are unsigned big-endian;
EOF must follow the final frame.

`scanBatch()` checks sequence numbers and lengths before allocating input buffers,
uses `io.ReadFull()` to detect truncation, and checks the final byte count and EOF.
Limits include 2 MiB per input, 32 MiB of original input, and 64 MiB of framed
transport. UTF-8 validation, control-character restrictions, and the
[LFS pointer policy](limitations.md#lfs-pointer-recognition) apply independently
in the adapter and runner. Missing, reordered, truncated, or extra data refuses
the scan instead of yielding a clean result.

A path and its file contents are independent text inputs. The end of one file
cannot combine with the start of another to form a detection match. Input counts
therefore differ from file counts; the adapter's 1,000-object budget is also
distinct from the frame count.

Python currently holds the accepted inputs and builds the framed byte array in
memory before sending it. Go reads one frame at a time, but this is not an
end-to-end constant-memory streaming implementation. Payload size limits are not
hard limits on total process memory.

## Inspecting one input in Go

`scanInput()` creates an upstream source backed by an in-memory reader:

```go
source := &sources.File{
    Content: bytes.NewReader(
        append([]byte("source002 text input\n"), data...),
    ),
}
```

Despite its name, `sources.File` does not create a payload file here. Its
`Fragments()` method consumes the reader and supplies fragments to a callback.
The callback passes each fragment to `detector.DetectContext()`, collects only
its finding rule IDs, and propagates errors or cancellation. Rule IDs are
deduplicated and sorted for each input; they are not counts of secret occurrences.

### Upstream fragmentation and the fixed text prefix

The runner reuses the upstream stdin fragmenter rather than treating every input
as one unrestricted string. The pinned implementation starts with a 100,000-byte
buffer and adjusts read boundaries. This preserves the existing stdin-oriented
scan policy, including its chunking limitations. See the pinned upstream
[source reader](https://github.com/gitleaks/gitleaks/blob/v8.30.1/sources/file.go).

The fixed `source002 text input` prefix prevents content-based MIME recognition
from silently skipping otherwise supported text, such as text beginning with
`%PDF`. It does not permit arbitrary binary data: text validation occurs first.
The prefix changes only the in-memory scan input, not Git objects or user files.

The prefix and payload use one contiguous `bytes.Reader`. An `io.MultiReader`
over separate prefix and payload readers can return only the prefix on its first
read, introducing an artificial fragment boundary. Keeping one reader avoids
that additional boundary inside the original text.

Original file paths are not supplied as fragment path metadata. Scanning names
as separate text inputs does not reproduce original-path-aware rules from
`gitleaks git` or `gitleaks dir`.

### Error propagation and detector reuse

The wrapper deliberately does not use upstream `DetectSource()` as its outer
scan loop. That convenience method has a log-and-continue path for fragment
errors. Here, an error, no emitted fragments, or an expired context returns an
incomplete result. See the pinned upstream
[detector implementation](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/detect.go).

`DetectContext()` returns each fragment's findings directly. The wrapper extracts
their rule IDs without adding them to the detector's shared findings collection.
One initialized detector is reused, but finding collection is local to each
input. Upstream logging is discarded so detailed errors and matched values do
not become the wrapper's output.

## Completion evidence and deadlines

Only after all inputs, byte totals, EOF, and context state pass validation does
Go emit a JSON report with `complete: true`. An illustrative finding report is:

```json
{
  "version": 1,
  "complete": true,
  "processed": 3,
  "bytes": 120,
  "findings": [{"input": 2, "rules": ["private-key"]}]
}
```

The report contains no raw paths or matched values. Python independently checks
the schema, version, completion flag, expected input and byte counts, finding
indexes, rule identifiers, and consistency with the exit status. Scanner stdout
and stderr are captured rather than forwarded to the user.

| Runner exit | Meaning | Adapter outcome |
| --- | --- | --- |
| `0` with a valid clean report | Complete, no findings | Hook exit `0` |
| `10` with a valid finding report | Complete, findings | Hook exit `1` |
| `2`, unexpected termination, or invalid/inconsistent report | Incomplete | Hook exit `2` |

A zero exit status with a missing or partial report is not success. Finding an
issue does not end the batch early; a later incomplete input still prevents a
complete report. Combined mode permits Git only when all scheduled adapters
return zero; push always schedules both.

Each Go input has a 10-second context, and the Go batch has a 120-second context
created after detector initialization. These are cooperative cancellation
deadlines, not OS process-kill guarantees. The Python adapter separately applies
its 120-second deadline to enumeration and execution, using the remaining time
for the runner. Combined mode grants each engine its own budget; it is not a
single 120-second budget shared by both engines.

## Docker lifecycle and trusted build

[docker_gitleaks.py](../scripts/docker_gitleaks.py) builds a local `scratch` image
from exactly the reviewed runner and policy file, plus its fixed Dockerfile.
There is no Go compiler, official CLI, shell, package manager, or repository
content in the image. Go is needed on the build machine, not during hooks.
Acquisition, build pins, and offline build commands remain in [runner.md](runner.md).

At runtime the adapter uses the recorded immutable image ID, with no network,
mounts, or implicit pulls. It sets a non-root user, a read-only filesystem,
dropped capabilities, no new privileges, one CPU, 256 MiB memory with no
additional swap, a 64-PID limit, and no container log storage. Payload bytes
travel through stdin, not a payload file or image layer.

After attaching to the container, the adapter inspects its actual exit state.
A running container, OOM kill, runtime error, or unacceptable exit code refuses
the scan. Once an exact daemon-issued container ID is available, a `finally`
block attempts to remove that container; cleanup failure also refuses. Hard
termination or daemon failure can prevent removal. Images remain available for
later scans and other consumers. There is no automatic native fallback. See
[docker.md](docker.md) for lifecycle details and cleanup boundaries.

The host Git/Python environment, installed bundle, Go toolchain and dependencies,
and Docker daemon remain trusted. Digest pinning detects a different artifact;
it is not independent proof of publisher identity or absence of vulnerabilities.
The Go runtime's 160 MiB memory target is soft, unlike Docker's hard memory limit.

## Limits of this design

Batching removes repeated startup work; it does not make secret detection
exhaustive. Unknown or encoded secrets, upstream allowlists, and fragmentation
limitations can still cause false negatives. Local hooks can be disabled or
bypassed and do not protect Web/API changes or other clones. Refusal does not
erase worktree files, staged objects, or history, and container isolation does
not hide plaintext process memory from a trusted host or daemon.

Do not use this implementation for unsupported platforms, binary or archive
inspection, workloads outside its fixed limits, or policies requiring original
file-path context. Do not silently narrow scope, raise limits, or change engines
after refusal. See [limitations.md](limitations.md) for the complete boundary and
[validation.md](../evals/validation.md) for recorded tests and their scope.
