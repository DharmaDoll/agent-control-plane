# Docker runtime for Gitleaks

Prefer this runtime when installing Gitleaks or combined checks. It isolates
Gitleaks from direct access to the repository and host credentials. Running an
arbitrary image with host mounts, mutable tags, or implicit pulls would introduce
different code and unnecessary access.

## Prerequisites and setup

Requires the already-installed `/usr/bin/docker`, a working local Linux x86_64
daemon at `unix:///var/run/docker.sock`, and the [verified batch runner](runner.md).
The skill does not install a daemon, modify group membership, use sudo, change
Docker contexts, or download software. Report missing prerequisites instead of
falling back to native execution. Host permission prompts remain applicable.

```sh
python3 -B scripts/manage_hooks.py inspect --repo /path/to/repository
python3 -B scripts/manage_hooks.py install --repo /path/to/repository \
  --engine combined --runtime docker --gitleaks-runner /path/to/verified/gitleaks-runner
python3 -B scripts/manage_hooks.py verify --repo /path/to/repository
```

Use `update --runtime docker` to migrate an existing managed Gitleaks/combined
installation, reusing its verified runner. Pre-batch installations must supply
`--gitleaks-runner` on the first update; their old CLI is not interchangeable.
For a Python-only installation, also select `--engine combined`. Ordinary updates retain the
existing runtime. Native mode requires an explicit user choice and
`--runtime native`. The Python-only engine does not support Docker mode.

## Build and placement

The manager verifies the binary before building. It sends a generated tar context
containing exactly a fixed Dockerfile, that binary, and the fixed configuration.
The image starts from `scratch`, with no base-image download, shell, package
manager, or build commands. Build networking and pulling are disabled. Repository
contents, Git history, credentials, and the ambient Docker CLI configuration are
not part of the build context.

The resulting immutable `sha256:` image ID is recorded in the versioned bundle's
`docker-image.json`. Docker manages image/layer storage; the executable inside
the container is `/gitleaks-runner`. The verified host copy remains under the bundle's
`bin/gitleaks-runner` for integrity checking and future rebuilds; Docker mode does not
execute that host copy. Rebuilding may reuse Docker's cache.

The image ID fixes the locally built image, not an independently signed upstream
container. Binary provenance still depends on the pinned acquisition evidence,
and the daemon and reviewed build procedure remain trusted.

## Scan invocation and failure

Git object enumeration and the custom Python scanner remain on the host.
The shared [image allowance](images-and-publication.md) uses only extensions and
byte budgets on the host. No decoder or worker runs. The Gitleaks image does not
receive content exempted by the image-extension policy.
Only the Gitleaks detector runs in Docker. All inputs for one hook are independently
framed through stdin to one container, with no repository, home, credentials,
or Docker-socket mounts. The detector is initialized once, not once per input.
The fixed policy includes:

- No network, no implicit image pulls, no ports, and no container log driver.
- Non-root UID/GID `65532`, read-only root filesystem, all capabilities dropped,
  and `no-new-privileges`.
- One CPU, 256 MiB memory with no additional swap, and 64 processes maximum.
- Fixed image ID, entrypoint, configuration, scanner options, and bounded CLI calls.

The adapter checks the actual container exit state, including OOM and running
state, rather than trusting attach output alone. Findings and incomplete/error
states refuse the Git operation. Scanner output remains redacted and validated
by the adapter. Daemon failure, missing image/manifest, or cleanup failure also
refuses; there is no native fallback.

After obtaining a daemon-issued container ID, the adapter removes that exact
container in a finally block, including after an attach timeout. Hard termination
or a daemon outage can prevent cleanup. A timed-out create/build may have taken
effect even without returning an ID; report uncertain completion rather than
blindly retrying or deleting by an assumed name.

Container startup and execution count toward the existing 120-second hook
deadline; attach uses the remaining budget, not a per-input 15-second timeout.
The existing size/scope limits still apply; this
runtime is unsuitable for workloads that cannot complete within those limits.
Remote Docker daemons, alternate sockets, unsupported architectures, and arbitrary
third-party images are outside this implementation.

## Cleanup and verification

The normal manager `verify` checks bundle integrity/configuration and exercises
the selected image through real local commit/push probes. A successful build or
image inspection alone is not evidence of working hooks.

`uninstall` and bundle `cleanup` retain Docker images because other repositories
or rollback bundles may use the same image. Cleanup reports known image IDs as
`docker_images_retained`; save this report before removing the bundle records.
Build failures can also leave images/cache in the daemon without an active bundle.
No `docker system prune`, image prune, or automatic shared-image deletion is used.
Image/cache deletion requires a separate request and inspection of consumers,
including inactive/rollback bundles in other repositories. A local container
list alone does not establish that an image is unused.

Temporary scan containers carry the label
`org.agent-control-plane.secret-checks=gitleaks`. For abandoned containers, inspect
the exact ID, label, image, and state before proposing removal. The label alone
is not authority to delete all matching resources.

Docker configuration semantics are documented in the
[container CLI reference](https://docs.docker.com/reference/cli/docker/container/run/)
and [base-image guide](https://docs.docker.com/build/building/base-images/).
Container isolation does not make Docker daemon access unprivileged or prevent
hook bypass and unknown-secret false negatives.
