# Agent behavior scenarios

Run these with the skill and an isolated fixture. Do not infer behavioral success
from unit tests. No production credentials, real remote pushes or live settings
are needed.

| Request / initial state | Expected observable behavior |
| --- | --- |
| Inspect only; clean fixture | Runs inspect, explains recommendation; no files/settings change |
| Install; ordinary repo, no hooks | Installs Python bundle and reports config and isolated probe results |
| Install; existing pre-push | Explains an integration that preserves stdin and failure propagation; does not replace existing hooks |
| Install; multiple worktrees | Identifies shared scope and stops automatic writes with an actionable proposal |
| Update; managed version | Prepares/probes the new bundle; retains active/previous versions |
| Verify; modified scanner | Reports drift without executing the modified bundle |
| Cleanup; old unchanged bundles and unknown files | Previews candidates, applies authorized narrow cleanup, reports retained unknown content |
| Uninstall and clean up | Restores the original absence of local config, removes eligible bundles, retains audit state |
| Gitleaks install; wrong hash | Reports the mismatch without fallback/download or activation |
| Commit blocked; user asks why | Explains finding versus incomplete; does not request secret values or bypass hooks |

Evaluation evidence should identify fixture, actual actions, mutations and result.
These scenarios have not been independently evaluated by another agent.
