# Static images and publication limits

## Purpose and boundary

Text-only scanning previously refused ordinary image fixtures even on unrelated
commits. Both engines now share deterministic image validation and publication
budgets. This permits normal static images while stopping unusually large
additions or pushes. It is not OCR, PII detection, malware scanning, or a proof
that an image contains no private data. No per-image approval list is maintained.

## Accepted images

| Extensions | Validation |
| --- | --- |
| `.png` | PNG decoder; reject APNG |
| `.jpg`, `.jpeg` | JPEG decoder |
| `.webp` | WebP decoder; one frame, no animation |
| `.bmp` | BMP decoder |
| `.gif` | GIF decoder; one frame |
| `.tif`, `.tiff` | TIFF decoder; one page |
| `.heic` | HEIC decoder; one primary image, no sequences, auxiliary/depth images or thumbnails |
| `.svg` | Restricted UTF-8 SVG XML; never rendered and still secret-scanned |

Raster input must match the extension's decoder, pass dimensions/frame checks,
verification where provided by the decoder, and full pixel decoding. Header-only
recognition is insufficient. Decoders can tolerate some unusual/trailing bytes;
successful decoding is not canonicalization or a guarantee against polyglots.
Files are never rewritten. Other non-text input remains unsupported. Filename
checks still run, including when the same blob appears under multiple extensions.

Each image is limited to 5 MiB and 20 million pixels. One process checks each
distinct format/content pair, with a 10-second parent timeout, 8-second CPU limit,
512 MiB address-space limit, no core dumps and no regular-file output. Per-engine
image validation is bounded to 1,000 distinct pairs and 50 MiB. Existing overall
hook deadlines remain in force. Large legitimate image collections can exceed
those budgets; errors do not cause a skip or fallback.

Raster pixels and metadata are NOT sent to either text secret detector. Successful
checks report `POLICY images_allowed:N image_content:unscanned`; N is the number
of distinct validated raster format/content pairs, not necessarily path count.
Messages and refs never receive an image exemption. SVG stays subject to existing
text size limits and both engines' ordinary secret checks.

SVG allows basic static shapes, paths, text, groups, gradients, local fragment
references, clipping and markers. It requires the SVG namespace and finite
positive dimensions or a viewBox. DTDs/entities, processing instructions other
than the XML declaration, foreign namespaces/content, scripts, event handlers,
animation, stylesheets/inline CSS, external references and embedded image/data
URIs are refused. XML nesting is capped at 64 levels and 10,000 elements. The
validator never resolves external resources or renders a document. This is a
restricted subset, not support for arbitrary browser-renderable SVG.

## Explicit decoder preparation

Image validation uses the host hook interpreter in a resource-limited child
process. It does NOT run in the Gitleaks container. The worker reads stdin only,
uses no network API and suppresses Python/native decoder diagnostics. Resource
limits are not isolation against a compromised native decoder: the host account,
interpreter, packages and native libraries remain trusted.

The reviewed environment is CPython 3.10 on Linux x86_64 with Pillow 12.3.0,
pillow-heif 1.8.1 (libheif 1.23.6 with libde265), and defusedxml 0.7.1. Versions and
required codec capabilities are checked at runtime. The wheel hashes are pinned
in [image-requirements.txt](../assets/image-requirements.txt). Other environments
require a separately reviewed dependency lock, not removal of hash checks.

Only after approval, create a dedicated environment at an explicit durable path
and acquire these wheels through an approved package source. For an already
approved local wheel directory, from the skill directory:

```sh
/path/to/python3.10 -m venv /approved/secret-checks-venv
/approved/secret-checks-venv/bin/python -m pip --isolated install \
  --no-index --find-links /approved/wheels --only-binary=:all: \
  --require-hashes -r assets/image-requirements.txt
/approved/secret-checks-venv/bin/python -I -B scripts/image_worker.py --check
```

No hook or management command creates the environment, downloads packages, or
installs system codecs. Missing/mismatched codecs refuse validation. Run the
manager with this interpreter when installing/updating: generated hooks retain
the venv executable path without resolving it to the base Python symlink target.
Keep that environment available while any active or rollback bundle uses it.
Bundle cleanup does not remove the externally owned environment or wheel cache.
Installation probes include a valid PNG and fail activation without the decoder
environment. Older rollback bundles retain their original text-only probes.

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
all index content/full reachable history, except validated raster contents.
The Python engine retains changed-blob/introduced-history scanning. Existing
text, object, transport and execution budgets still apply and may stop a check
below the publication limit. Budgets are fixed in reviewed code/bundles; no
repository config, inline comment or environment variable raises them.

Diagnostics contain only fixed codes and counters, for example:

```text
ERROR policy commit-files actual:101 limit:100
ERROR policy image-decoder-unavailable
```

Combined mode forwards only allowlisted policy lines with an engine label. Other
child diagnostics, findings and raw paths remain suppressed. Findings exit 1;
budget violations, unsupported input and incomplete checks exit 2. Neither
permits Git to continue.

## Verification and unsuitable uses

Use isolated synthetic images, not personal documents, for tests. Cover every
format, malformed/renamed input, frames/pages, decompression limits, unsafe SVG,
staged-versus-worktree behavior, file-name checks, image plus secret text,
intermediate history, multi-ref updates and threshold boundaries. Validate the
selected Docker runtime separately; a successful native run is not Docker proof.

This control cannot detect faces, screenshots of personal records, QR codes,
metadata secrets, small sensitive text datasets without matching secret patterns,
or deliberate uploads split below thresholds. Local hooks remain bypassable and
do not protect Web/API writes. Do not use it as a DLP guarantee or as a sanitizer
for serving untrusted images on a website. Rejection does not erase local Git
objects or revoke already exposed credentials. Prefer a separately reviewed
workflow when full document/PII inspection or larger workloads are required.

Decoder behavior is documented by [Pillow](https://pillow.readthedocs.io/en/stable/reference/Image.html),
[pillow-heif](https://pillow-heif.readthedocs.io/en/latest/reference/HeifFile.html),
and [defusedxml](https://pypi.org/project/defusedxml/).
