# Combined engine

Use `--engine combined` when both the custom Python policy and pinned Gitleaks
detection are required. Either engine alone can miss patterns recognized by the
other. Running one only after the other fails would leave successful scans with
just one engine's coverage.

## Execution

For each managed `pre-commit`, `commit-msg`, and `pre-push` hook:

```text
Git hook
  -> combined_gate.py
     -> scan_sensitive.py   (Python policy)
     -> gitleaks_gate.py    (pinned Gitleaks)
  -> allow only if both return 0
```

The dispatcher runs Python first, then Gitleaks even after a finding or child
failure. Invalid invocation or unavailable/oversized push input stops before
either child runs. It reads pre-push stdin once (64 KiB maximum, five-second read
deadline), then sends the identical bytes to both children. It passes the commit
message path as one argument without invoking a shell. Each child retains its
own scope, budgets, and 120-second deadline; the dispatcher additionally bounds
each child to 125 seconds and kills its process group on that timeout. Combined
checks can therefore take roughly twice as long as a single engine.

Child stdout/stderr are discarded, including unexpected errors. Output contains
only `CHECKED`, `REJECTED`, or `ERROR` and the fixed engine name. Per-rule and
location diagnostics from the Python engine are not forwarded in this mode.
Exit 0 requires both successes; exit 1 means findings with no incomplete check;
exit 2 means at least one incomplete/error result, including unexpected child
exit codes or a missing child. There is no fallback to a single engine.

## Setup and migration

Prepare the [verified batch runner](runner.md) first. From the skill directory:

```sh
python3 -B scripts/manage_hooks.py inspect --repo /path/to/repository
python3 -B scripts/manage_hooks.py install --repo /path/to/repository \
  --engine combined --runtime docker --gitleaks-runner /path/to/verified/gitleaks-runner
python3 -B scripts/manage_hooks.py verify --repo /path/to/repository
```

For an existing managed Python installation, use `update` instead of `install`
with the same engine/runner arguments. An existing batch-enabled Gitleaks or combined bundle
can supply its already verified runner when `--gitleaks-runner` is omitted.
Pre-batch bundles require that argument on their first migration. The manager
verifies the pinned digest again; it never downloads a binary or falls back.
Ordinary updates preserve the selected engine. The initial default remains
Python for compatibility; copying this skill does not change installed hooks.

Prefer [Docker execution](docker.md) for Gitleaks. Python policy and Git object
enumeration still run on the host. New Gitleaks/combined installations default to
Docker; existing installations preserve their runtime unless `--runtime` changes
it explicitly. Docker failures never select native execution.

Installation, verification, and rollback probe the exact bundle in temporary
Git repositories. In combined mode the probes require both engines' success
markers on safe operations and both engines' refusal markers for the shared
secret/message/history canary and unscannable input. One working engine must
not hide the other engine's failure to detect the probe.

The bundle includes the dispatcher, both scanners, fixed Gitleaks configuration,
verified binary, and three hooks. [Rollback and cleanup](installation.md) cover
these recorded files just like single-engine bundles.

## Scope and residual risks

Both engines' restrictions apply. Gitleaks scans all regular index blobs at
pre-commit and full reachable history at pre-push; Python retains its changed-blob
policy and filename rules. Combined mode rejects tags/non-branch destinations
because Python does not support them, even though Gitleaks alone does. Gitleaks'
2 MiB input limit can reject content that fits Python's 5 MiB limit. Individual
budgets are not pooled and one successful result cannot waive another refusal.

Do not use combined mode where the verified binary/platform is unavailable,
required inputs exceed either engine's supported scope, or the extra latency is
unacceptable. Choose a separately reviewed design rather than bypassing failures.

Both engines run locally, without LLM decisions or credential-validity API calls.
They share the same trusted OS account, Git, interpreter, bundle, and Git state;
they are not independent security boundaries. No lock freezes index/message/ref
data across both scans. Local concurrent edits, runtime compromise, hook bypass,
unknown/encoded secrets, and false positives remain possible. Two successful
scans do not guarantee absence of leaks. See [limitations.md](limitations.md)
for controls outside local hooks, including Web/API publication.
