"""Local Docker execution with fixed inputs, no mounts, and no implicit pulls."""
import io
import json
import re
import subprocess
import tarfile
import tempfile

DOCKER = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
DOCKERFILE = b"""FROM scratch
COPY gitleaks /gitleaks
COPY gitleaks.toml /gitleaks.toml
USER 65532:65532
ENTRYPOINT ["/gitleaks"]
"""


def command(args, *, data=None, timeout=15):
    # An empty CLI config prevents ambient contexts, auth helpers and proxies.
    with tempfile.TemporaryDirectory(prefix="secret-checks-docker-cli-") as config:
        try:
            return subprocess.run(
                [*DOCKER, "--config", config, *args], input=data,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("DOCKER_UNAVAILABLE_OR_TIMEOUT") from None


def build_image(binary, configuration):
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode="w") as archive:
        for name, content, mode in (("Dockerfile", DOCKERFILE, 0o444),
                                    ("gitleaks", binary, 0o555),
                                    ("gitleaks.toml", configuration, 0o444)):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(content), mode, 0
            archive.addfile(entry, io.BytesIO(content))
    result = command(["build", "--quiet", "--network=none", "--pull=false",
                      "--label", "org.agent-control-plane.secret-checks=gitleaks", "-"],
                     data=context.getvalue(), timeout=120)
    identity = result.stdout.decode("ascii", errors="replace").strip()
    if result.returncode or not IMAGE_ID.fullmatch(identity):
        raise RuntimeError("DOCKER_IMAGE_BUILD_FAILED")
    verify_image(identity)
    return identity


def verify_image(identity):
    if not isinstance(identity, str) or not IMAGE_ID.fullmatch(identity):
        raise RuntimeError("INVALID_DOCKER_IMAGE_ID")
    result = command(["image", "inspect", "--format", "{{.Id}}", identity])
    if result.returncode or result.stdout.strip() != identity.encode():
        raise RuntimeError("DOCKER_IMAGE_UNAVAILABLE")


def scan(identity, arguments, data):
    verify_image(identity)
    # Create first so cleanup can target an exact daemon-issued ID, not a name.
    created = command([
        "create", "--pull=never", "--interactive", "--network=none", "--read-only",
        "--user=65532:65532", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=64",
        "--memory=256m", "--memory-swap=256m", "--cpus=1",
        "--label=org.agent-control-plane.secret-checks=gitleaks",
        "--log-driver=none", "--entrypoint=/gitleaks", identity, *arguments,
    ])
    container = created.stdout.decode("ascii", errors="replace").strip()
    if created.returncode or not CONTAINER_ID.fullmatch(container):
        raise RuntimeError("DOCKER_CONTAINER_CREATE_FAILED")
    try:
        result = command(["start", "--attach", "--interactive", container], data=data)
        # docker start's CLI status alone is not the scanner's exit status.
        state = command(["inspect", "--format", "{{json .State}}", container])
        if state.returncode:
            raise RuntimeError("DOCKER_CONTAINER_STATE_UNAVAILABLE")
        try:
            value = json.loads(state.stdout)
            if value["Running"] or value["OOMKilled"] or value["Error"]:
                raise ValueError
            code = value["ExitCode"]
            if type(code) is not int or code not in (0, 10):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("DOCKER_SCAN_INCOMPLETE") from None
        if result.returncode not in (0, code):
            raise RuntimeError("DOCKER_ATTACH_FAILED")
        return subprocess.CompletedProcess([], code, result.stdout, b"")
    finally:
        # Also stop a container when attach times out or the hook alarm fires.
        removed = command(["rm", "--force", container])
        if removed.returncode:
            raise RuntimeError("DOCKER_CONTAINER_CLEANUP_FAILED")
