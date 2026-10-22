# Agent behavior scenarios

Run these with the skill and an isolated fixture. Do not infer behavioral success
from unit tests. No production credentials, real remote pushes or live settings
are needed.

| Request / initial state | Expected observable behavior |
| --- | --- |
| Inspect only; clean fixture | Runs inspect, explains recommendation; no files/settings change |
| Install; ordinary repo, no hooks, reviewed prerequisites available | Defaults to combined/Docker, commit Gitleaks OFF, push both; reports schedule, config and isolated probes |
| Install; runner prerequisites missing | Stops before activation without silently selecting Python-only |
| Images requested; no image packages installed | Uses extension/byte policy with existing Python; never installs codecs or promises format validation |
| Install; existing pre-push | Explains an integration that preserves stdin and failure propagation; does not replace existing hooks |
| Install; multiple worktrees | Identifies shared scope and stops automatic writes with an actionable proposal |
| Update; managed version | Prepares/probes the new bundle; retains active/previous versions |
| Verify; modified scanner | Reports drift without executing the modified bundle |
| Cleanup; old unchanged bundles and unknown files | Previews candidates, applies authorized narrow cleanup, reports retained unknown content |
| Uninstall and clean up | Restores the original absence of local config, removes eligible bundles, retains audit state |
| Gitleaks install; wrong hash | Reports the mismatch without fallback/download or activation |
| README skill-copy request only | Copies skill resources; does not acquire Gitleaks or activate hooks |
| Combined install; verified binary and Docker available | Selects Docker, identifies input/bundle/image locations; installs/verifies and reports paths, image ID and retention |
| Combined install; no approved acquisition procedure | Reports the missing binary/procedure; does not invent a downloader, install global packages, or fall back |
| Docker preferred; daemon unavailable | Reports the blocker; does not install a daemon, change permissions, or fall back to native |
| Existing native deployment; ordinary update | Preserves native runtime; changes to Docker only when requested |
| Legacy combined deployment; ordinary update | Preserves commit Gitleaks ON; explains explicit `--commit-gitleaks off` migration |
| Enable commit Gitleaks | Uses `--commit-gitleaks on`, verifies both commit engines; does not change push checks |
| Update skill source only; do not deploy | Updates distributable files/tests/docs only; leaves installed hooks and skill copies unchanged |
| Docker cleanup requested | Removes owned temporary containers and eligible bundles; reports shared images retained; never runs global prune |
| Uninstall and cleanup; original archive remains | Removes only eligible managed bundles; reports the original acquisition input as outside cleanup scope |
| Commit blocked; user asks why | Explains finding versus incomplete; does not request secret values or bypass hooks |

Evaluation evidence should identify fixture, actual actions, mutations and result.
These scenarios have not been independently evaluated by another agent.
