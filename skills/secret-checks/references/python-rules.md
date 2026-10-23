# Python secret detection

## Purpose and boundary

The Python engine is a small, offline guard for common credential shapes and
publication policy. Its rules are deterministic; the agent neither classifies
each commit nor receives secret values. Pattern misses can still enter local
history. The default combined schedule adds Gitleaks at push, not at commit.
Neither engine proves that publishing data is safe.

The canonical definitions are `SECRET_RULES`, `CONTEXT_RULES` and
`matching_rules()` in [scan_sensitive.py](../scripts/scan_sensitive.py). There
are 32 regular-expression rule IDs, 14 explicit-field rule IDs, and two
structured checks (URL userinfo and Basic Authorization). Findings are deduplicated
per rule and input, sorted, and reported with hashed location labels only.
The same detector checks text content, target labels and outgoing destination
refs. Allowed raster-image bodies remain unscanned; their names are checked.

These are detection heuristics, not exact provider token validators. Distinctive
prefixes use alphabet/length constraints, sometimes deliberately broader than a
single issued format. Opaque credentials require an allowlisted assignment key.
Words mentioning a provider, arbitrary hexadecimal strings and public IDs do not
by themselves indicate a secret. Matching synthetic examples are also blocked.

## Service coverage

| Service | Standalone shapes or required context |
| --- | --- |
| GitHub | `gh[pousr]_`, `github_pat_` |
| GitLab | `glpat-`, `gldt-`, `glrt-`, `glrtr-`, including bounded routable suffixes; custom prefixes are not enumerated |
| AWS | `AKIA`/`ASIA` access IDs and `(aws_)secret_access_key` assignments |
| Google Cloud | `AIza` API keys; private keys use the generic PEM-header rule |
| OpenAI | `sk-proj-`, `sk-svcacct-`, `sk-admin-`, legacy marker-bearing keys; `OPENAI_API_KEY` |
| Anthropic | `sk-ant-api03-`, `sk-ant-admin01-`; `ANTHROPIC_API_KEY` |
| Hugging Face | `hf_`, `api_org_`; `HF_TOKEN`, `HUGGINGFACE_TOKEN` |
| Azure | `AZURE_CLIENT_SECRET`, `AZURE_STORAGE_KEY`, connection-string `AccountKey`, SAS assignment fields; Azure Storage URLs containing a signature |
| Cloudflare | Explicit `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_API_KEY` and `CF_` aliases |
| npm / PyPI | `npm_`, registry auth assignments, `pypi-` |
| Docker Hub | `dckr_pat_` |
| Vercel | `vcp_`, `vci_`, `vca_`, `vcr_`, `vck_`; `VERCEL_TOKEN`, `VERCEL_API_TOKEN` |
| Netlify | `NETLIFY_AUTH_TOKEN`, `NETLIFY_API_TOKEN` |
| Supabase | `sb_secret_`; `SUPABASE_SERVICE_ROLE_KEY`, `service_role_key`; legacy JWTs also match the generic JWT rule |
| DigitalOcean | `dop_v1_`, `doo_v1_`, `dor_v1_` |
| Slack | `xox[bpars]-`, `xapp-`, incoming webhook URLs |
| Discord | Credential-bearing webhook URLs; `DISCORD_TOKEN`, `DISCORD_BOT_TOKEN`, `DISCORD_CLIENT_SECRET` |
| Notion | `ntn_`; legacy `secret_` under explicit Notion credential fields |
| Atlassian | `ATATT3`; `ATLASSIAN_API_TOKEN`, `JIRA_API_TOKEN`, `CONFLUENCE_API_TOKEN` |
| Linear | `lin_api_` |
| Stripe | `sk_`/`rk_` test/live/prod secrets and `whsec_` signing secrets, not `pk_` publishable keys |
| SendGrid / Resend | `SG.` two-segment keys; `re_` |
| Datadog | Explicit `DD_API_KEY`/`DATADOG_API_KEY` (32 hex), app/application key aliases (40 hex) |
| Grafana | `glsa_`, `glc_`; `GRAFANA_API_KEY`, `GRAFANA_TOKEN` for legacy opaque keys |
| Vault | `hvs.`, `hvb.`; legacy `s.` under `VAULT_TOKEN` |

Supabase `sb_publishable_`, Stripe `pk_`, Discord client IDs and Azure tenant IDs
are not new secret patterns. This is **not a global allowlist**: an existing rule
can still reject the same input. In particular, a public legacy Supabase `anon`
JWT still matches the generic JWT rule; no role-based JWT exemption is added.
An opaque token stored under an unknown field may be missed. No cloud inventory,
provider API, entropy model or credential validity check is used.

## Assignments, URLs and Basic headers

Generic assignments recognize selected exact names such as `password`, `token`,
`client_secret` and `api_key`, with the existing minimum of 12 matching value
characters. Names are case-insensitive. JSON quoted keys, inline objects and
shell `export` are supported without parsing or executing those languages.
Explicit service fields use their own value constraints. Suffixes such as
`MY_PASSWORD_DOC` and public client IDs are not generic credential names.
The scanner is not a complete JSON, shell or programming-language parser; escaped
keys, string concatenation, unusual names and other obfuscation can be missed.

`credential-url` recognizes password-bearing userinfo in HTTP(S), PostgreSQL,
MySQL, MongoDB (including `+srv`) and Redis URLs. Only userinfo passwords are
percent-decoded, once; URLs are never fetched or resolved. Empty passwords,
username-only URLs and complete `$VARIABLE`/`${VARIABLE}` passwords do not match
this rule. Short literal passwords do match. Recognized credential-bearing
authorities over 4,096 bytes are incomplete, not clean. Azure SAS URL matching is
a separate bounded heuristic for standard Storage endpoints, with at most 4,096
characters between the first slash and the signature parameter. Sovereign-cloud
hosts and longer SAS URLs are not comprehensively covered.

`basic-auth` recognizes `Authorization` and `Proxy-Authorization` headers,
including quoted keys/values. It validates Base64 with the standard library,
decodes at most 4,096 encoded bytes, then requires a colon and a nonempty literal
password. Empty usernames are permitted. Invalid Base64, a missing colon or an
empty/reference password does not match this rule. A recognized candidate over
4,096 bytes stops with exit 2. No arbitrary Base64 bodies, nested encodings or
authentication attempts are processed. Decoded bytes stay in process memory and
are never printed or deliberately persisted; secure memory erasure is not claimed.

These exclusions apply to the specific rule only. The full set of rules still
runs, including on environment-template contents. No `example`/`dummy` text,
whole-file exclusions, configurable bypasses or automatic redaction are added.

## Maintenance and evidence

Before adding a rule, establish a distinctive structure or explicit field name,
add inert positive/negative/boundary fixtures, and check output suppression.
Fixtures assemble token-shaped bytes at runtime; do not paste real credentials.
Keep `inert_samples()` aligned with every regex rule and cover every contextual
field. Run real index/message/history hooks, the complete regression suite, and
[benchmark_python.py](../evals/benchmark_python.py) before accepting changes.
The benchmark probes 5 MiB synthetic text with a 10-second per-probe deadline;
it is a local regression check, not a performance or security guarantee.

The byte/item/time budgets and image/publication policy are unchanged. Rule
expansion costs CPU and may increase false positives. Do not use this engine as
a standalone DLP system, image/OCR scanner, server-side enforcement boundary, or
replacement for credential revocation after exposure. A skill copy does not
update active hooks: request a managed update and verification separately.

Format references reviewed for this expansion (not runtime dependencies):

- [Gitleaks v8.30.1 rule catalog](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/gitleaks.toml)
  for provider token shapes; Python rules are curated independently and do not
  claim identical coverage or execute a comparative Gitleaks evaluation.
- [GitLab token overview](https://docs.gitlab.com/security/tokens/),
  [Slack token types](https://docs.slack.dev/authentication/tokens/) and
  [npm token format](https://github.blog/changelog/2021-09-23-npm-has-a-new-access-token-format/).
- [Vercel token formats](https://vercel.com/changelog/new-token-formats-and-secret-scanning)
  and [Supabase secret versus publishable keys](https://supabase.com/docs/guides/getting-started/api-keys).
- [Docker token format](https://docs.docker.com/reference/api/ai-governance/),
  [Resend CLI authentication](https://github.com/resend/resend-cli) and
  [Netlify CLI authentication](https://docs.netlify.com/api-and-cli-guides/cli-guides/get-started-with-cli/).
- [RFC 7617](https://www.rfc-editor.org/rfc/rfc7617) for Basic credentials and
  [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986) for URL userinfo.

Executed results and unverified environments are recorded in
[validation.md](../evals/validation.md).
