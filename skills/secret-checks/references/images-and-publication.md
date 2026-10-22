# Image allowances and publication limits

## Purpose and boundary

The goal is to keep ordinary image commits usable and stop unusually large
publication, not to validate image format or rendering safety. Earlier decoder
checks added native dependencies and a dedicated Python environment beyond that
goal. The current policy uses the existing Python standard library only.

## Extension-based allowance

Files with these case-insensitive final suffixes receive an explicit content
exemption: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`,
`.tif`, `.tiff`, and `.heic`. SVG is not exempt: it remains ordinary text
subject to the existing secret checks and text limits.

No magic-byte, decode, corruption, pixel-count, frame-count or page-count checks
are performed. Even empty or incorrectly named contents are allowed within the
byte budgets. This is not a static-image-only policy. Each exempted input is
limited to 5 MiB. Per engine, image accounting retains a 50 MiB / 1,000 distinct
extension-family/content-pair budget; aliases such as jpg/jpeg share a family.
Repeated identical contents in a family are counted once for this accounting.
The commit/push publication counts below are independent and still include images.

Names remain subject to ordinary filename/secret-pattern checks. Exempted content
is not sent to either text secret detector. Messages and refs never receive the
image exemption. A blob used under both an allowed image suffix and a text path
must still undergo text scanning for the latter path.

The diagnostic `POLICY images_allowed:N image_content:unscanned` reports distinct
allowed family/content pairs, not certified images or necessarily path count.
No image decoder process, network API, OCR or external Python package is used.
Git and Gitleaks keep their existing execution and error boundaries.

## Installation and legacy environments

New bundles use an existing Python 3.10+ interpreter and include
`publication_policy.py`, but no `image_worker.py`. No dedicated venv, Pillow,
pillow-heif or defusedxml installation is required. Gitleaks still requires its
verified runner and selected Docker/native runtime.

Updates use the explicitly chosen interpreter; merely copying the skill does
not update existing hooks. Earlier decoder-based bundles retain their original
code, interpreter and dependency requirements when rolled back. Keep their
environment while active/rollback consumers exist. The manager recognizes the
old worker file for integrity checks and authorized bundle cleanup, but does not
copy it into new bundles or delete externally owned environments/packages.
Never automatically remove a venv, global package or another repository's hooks.
Installation/verification still probe a PNG-named input and ordinary text.

## Publication budgets

| Operation | Count limit | Byte limit |
| --- | --- | --- |
| Commit | 100 added/modified/renamed/type-changed regular index paths | 20 MiB of full target blob contents, counted per path |
| Push | 500 distinct newly reachable blobs across all updated refs | 50 MiB of their full contents, counted once per blob |

Equality is allowed; exceeding either limit refuses the operation. Pure deletion
adds no bytes. A rename counts as an affected path at commit. Shared contents at
different paths count per path at commit, but once per blob for push. These are
logical file sizes, not compressed Git transfer sizes, personal-record counts,
or cumulative rate limits across operations.

Commit checks inspect the index and do not charge all unchanged existing files
to the publication budget. Push checks use each update's actual old/new OIDs,
not remote-tracking refs. They union the objects newly reachable from each new
tip relative to its corresponding old tip, including intermediate/deleted
versions. A new ref has no trusted baseline and includes full reachability even
if another remote branch might already contain those objects. Force updates use
the same set-difference rule; deletion-only updates have no new objects. Missing
old objects, malformed input or enumeration limits cause refusal, never fetch.

Publication limits do not replace secret-scanning scopes. Gitleaks still scans
all index content/full reachable history when scheduled, except contents of allowed image extensions.
The Python engine retains changed-blob/introduced-history scanning. Existing
text, object, transport and execution budgets still apply and may stop a check
below the publication limit. Budgets are fixed in reviewed code/bundles; no
repository config, inline comment or environment variable raises them.

Diagnostics contain only fixed codes and counters, for example:

```text
ERROR policy commit-files actual:101 limit:100
ERROR policy image-bytes-limit
```

Combined mode forwards only allowlisted policy lines with an engine label. Other
child diagnostics, findings and raw paths remain suppressed. Findings exit 1;
budget violations, unsupported input and incomplete checks exit 2. Neither
permits Git to continue.

## Verification and unsuitable uses

Test every listed extension, uppercase suffixes, arbitrary/corrupt bytes, empty
inputs, size and aggregate limits, unchanged paths, secret-like filenames,
message inputs, SVG secret detection, and the same blob under image/text names.
Test installation/update/verify using Python without third-party packages.
Exercise combined mode and the selected Docker runtime separately.

Extension-based exemption deliberately accepts files that are not valid images,
animation, multipage files and payloads disguised as images. It does not inspect
pixels, metadata, OCR text, QR codes, embedded resources, or personal records.
SVG receives text secret checks, not XML parsing, rendering or sanitization:
scripts, external references and encoded content are not comprehensively checked.
Use an application's own image/SVG handling policy before rendering untrusted
files; this hook is not an upload-safety or malware-scanning boundary.

Small sensitive datasets, split uploads below thresholds, unknown secret formats,
and deliberate bypasses can escape detection. Local hooks do not protect Web/API
writes or other clones. Refusal does not erase local Git objects or revoke
already exposed credentials. Do not use this as a DLP guarantee or as proof that
a file is safe to display.
