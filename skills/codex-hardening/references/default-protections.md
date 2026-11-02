# Default protections and explicit exceptions

Read before setup or relaxing a protection. These controls reduce accidental
credential reads and risky command approvals; they do not provide global DLP.

## Credential catalogue

Both review and development profiles deny reads and writes at these locations.
`~` in the plan means the explicit `--user-home`, **not** `--codex-home`.
Installed profiles use absolute paths. The manager never opens these files or
searches for credential values.

| Opt-out ID | Paths below the user home |
| --- | --- |
| `ssh` | `.ssh/`, including configuration and public keys |
| `aws` | `.aws/`, including config, credentials, CLI and SSO caches |
| `gcloud` | `.config/gcloud/`, including local ADC and CLI stores |
| `azure` | `.azure/` |
| `oci` | `.oci/` |
| `kubernetes` | `.kube/` |
| `docker` | `.docker/config.json` |
| `containers` | `.config/containers/auth.json` |
| `terraform` | `.terraform.d/credentials.tfrc.json`, `.terraformrc` |
| `pulumi` | `.pulumi/credentials.json` |
| `vault` | `.vault-token` |
| `github` | `.config/gh/hosts.yml` |
| `gitlab` | `.config/glab-cli/config.yml` |
| `git` | `.git-credentials`, `.config/git/credentials` |
| `npm` | `.npmrc` |
| `pypi` | `.pypirc` |
| `netrc` | `.netrc` |
| `cargo` | `.cargo/credentials`, `.cargo/credentials.toml` |
| `gem` | `.gem/credentials` |
| `gnupg` | `.gnupg/` |
| `database` | `.pgpass`, `.my.cnf`, `.mylogin.cnf` |

This is a catalogue of default locations, not effective authentication discovery.
Alternate XDG paths, `AWS_SHARED_CREDENTIALS_FILE`, `CLOUDSDK_CONFIG`,
`AZURE_CONFIG_DIR`, `KUBECONFIG`, `DOCKER_CONFIG`, external service-account keys,
Windows stores, keyrings, environment credentials, agent sockets and workload
identity are not covered. Custom locations need separate review.

Blocking these files can prevent authenticated CLI operations. Explain that
impact before applying. Do not automatically retry outside the sandbox, extract
tokens into the environment, or copy credentials to unprotected locations.
Workspaces inside a protected path or containing the user home are blocked.
The latter layout exposed a native missing-path mount failure in 0.165.0; use
the intended project workspace rather than weakening a deny to make it start.

Default-location references: [AWS](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html),
[Google Cloud](https://docs.cloud.google.com/sdk/docs/configurations),
[Azure](https://learn.microsoft.com/cli/azure/azure-cli-configuration),
[OCI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm),
[Kubernetes](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/),
[Docker](https://docs.docker.com/reference/cli/docker/),
[Terraform](https://developer.hashicorp.com/terraform/cli/config/config-file),
[Pulumi](https://www.pulumi.com/docs/iac/concepts/state-and-backends/).

## Separate home-wide command rules

`--mode command-rules` manages `<codex-home>/rules/acp-hardening.rules`. These
rules affect sessions using that home, not just the managed profiles. Propose
both components during default setup, but obtain approval for each scope.

- `sudo`: forbidden prefixes `sudo`, `/bin/sudo`, `/usr/bin/sudo`.
- `rm`: prompt prefixes `rm`, `/bin/rm`, `/usr/bin/rm`, including ordinary removal
  to avoid relying on flag order for the ask rule. Common recursive prefixes
  targeting `/` or the explicit user home are forbidden: `-rf`, `-fr`, `-r`,
  `-R`, `-f -r`, `-r -f`, `--recursive --force`, optionally followed by `--`
  immediately before the target.

This is not a universal deletion guard: other executable paths, wrappers,
flags, target aliases/trailing slashes, scripts or Python can perform equivalent
operations. Unmatched rm target forms fall back to prompt, not guaranteed deny.
Rules are command decisions, not an OS syscall filter; filesystem permissions
remain the underlying write boundary.

## Existing rules and opt-out

On 0.165.0 a file's existence alone no longer blocks. Only literal
`prefix_rule(...)` calls are accepted: strings/list unions, decisions, optional
justification and string-list match tests. Assignments, computed patterns and
other constructs stop with `UNREVIEWED_RULE_SYNTAX`. Python `ast` inspects syntax
without executing it. Native `execpolicy check` validates temporary snapshots
and inline tests. Originals remain untouched and participate in drift checks.

Candidate decision checks combine all collected existing rules. Stricter
restrictions stay in force. Inspect `existing_rule_allow_count` and `rule_warning`:
existing allows can run commands outside filesystem protections. Human review
must assess those grants; syntactic compatibility is not safety certification.
Project trust determines which rules Codex loads; this helper does not change it.

Use repeated `--disable-protection <ID>` only for human-approved exceptions.
Profiles accept credential group IDs; command-rules accepts `sudo` and `rm`.
There is no `all` or ignore-unknown switch. Opt-out removes only this manager's
entries, not another file's restrictions, and never adds an allow rule.
Repeat options for plan/apply/verify. Exceptions and the explicit user home are
bound into the plan ID. Generated files record disabled IDs. Changed options
or upgrades require a newly accepted plan; no existing installation auto-updates.

## Evidence boundaries

Profile verification checks installed bytes and the original sandbox probes,
then separately tests synthetic credential files in a temporary home. It never
opens real credentials or proves protection of all aliases, mounts or newly
created paths. Missing paths, hardlinks and pre-opened descriptors need separate
assessment. Original OS file permissions are unchanged.

Command verification tests native decisions without executing sudo or rm.
Approval UI, model sessions and startup rule-loading are NOT RUN. Restart Codex
after installation and verify live behavior separately. MCP, Web, other tools
and approved sandbox escapes remain separate boundaries. See
[official rules](https://learn.chatgpt.com/docs/agent-configuration/rules) and
[filesystem permissions](https://learn.chatgpt.com/docs/permissions).
