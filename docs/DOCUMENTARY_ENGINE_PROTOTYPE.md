# Documentary research and scene-composition prototype

This is the first independent engine increment toward the actual product: an
uploaded voice/story driving researched visuals, scene cuts, motion and editorial
graphics. Clip discovery/captions are supporting components, not the final editor.
The engine now also powers the [automatic documentary app pilot](AUTOMATIC_DOCUMENTARY.md).
That consented, allowlisted action uses photographs and source footage/voice.
The full Documentary style remains unfinished; this document describes the
lower-level engine and separate operator demonstration.

## Working components

- A closed, frame-exact storyboard covers the entire declared output with 2–8
  scenes, each 1–15 seconds. Total duration is 5–60 seconds, within the requested
  cap, at 1080×1920/30fps. Scenes are source footage, a licensed image, licensed
  video or an original editorial card. Unknown modules/effect code are rejected.
- Public-topic research can retrieve attributed Wikipedia search excerpts and
  Commons image/video candidates. This is retrieval, **not fact verification**.
  Queries are form POSTs so source-derived topic text is not put in request URLs.
  Private transcript/ASR text is not logged or automatically sent to this adapter.
- The first source set is deliberately restricted to source-declared CC0/public
  domain JPEGs and WebM footage. Unsupported, noncommercial, no-derivatives,
  share-alike and ambiguous licenses are excluded. The metadata is a provider
  assertion, not universal legal clearance; production review remains necessary.
- Each asset has an immutable content hash, creator, title, source page, download
  URL, retrieval time, license, kind and byte count. Original demo illustrations
  require an explicit ownership declaration and cannot masquerade as web assets.
  A model cannot forge download rights: only unchanged candidates actually issued
  by that research session can be downloaded.
- The compositor keeps one continuous original source voice interval underneath
  all scenes. External clip audio is discarded. It supports original-footage
  inserts, moving photos, video inserts, headline fade/slide motion and editorial
  cards with source labels. No user voice synthesis/cloning is enabled.
- Each scene is encoded separately. A final stream-copy composition combines the
  validated scenes and source voice, with no whole-video second video encode.
  Frames, dimensions, fps and final duration are checked before atomic publication.

The current demo uses a small authored storyboard/template. Gemini creative
storyboarding, automatic asset relevance/fact review, shot-aware cropping and a
finished Documentary style policy are **not completed by this prototype**.

## Security, limits and lifecycle

Search requires explicit consent. A session permits at most three searches and
three downloads, with 256 KiB metadata responses, 8 MiB images, 16 MiB videos and
24 MiB total downloaded asset data. Fixed HTTPS Commons/Wikipedia origins are
used; URLs with credentials, unexpected ports, queries or fragments are rejected.
Redirects are not followed. Encoded responses are refused rather than allowing
unbounded decompression. Provider errors expose only closed codes.

Rendering verifies local file hashes, source bounds and receipts. Source and
asset copies are bounded, verified and checked for cancellation. Every native
call retains file/format/codec restrictions, CPU limits and required sandbox
behavior. The only new sandbox capability is read access to at most eight exact
scene files and one voice WAV in the same private attempt as a fixed generated
concat manifest. No directory, network or additional write grant is introduced.
Symlinks, hardlinks and unexpected filenames are rejected. The output file remains
the only writable sandbox file for each native process.

The composition budget is at most 300 seconds, native stage timeouts at most
60 seconds, and the existing 30/60-second inspection ceilings are never increased.
The scene aggregate and final MP4 are each capped at 64 MiB; the source is capped
at 300 MiB and assets at 24 MiB. Attempt files are private and removed on success,
failure or cancellation. Existing output files are never replaced. Stage CPU/RSS,
wall time, scene count, frame count and output bytes are measured without logs of
transcript text, raw ASR/provider output or native stderr.

The operator prototype has no public API and no customer retention/entitlement
system of its own. Before app activation it must use the existing authenticated
job admission, storage reservations, owner consent, source snapshot, cancellation,
publication/deletion fencing, asset retention/deletion and cost/rate budgets.
It must not become an alternate unmetered or unauthenticated rendering endpoint.

## Reproduce the visible local proof

From the checkout, using the existing Python environment and system FFmpeg:

```bash
.venv/bin/python scripts/demo_documentary.py --output /tmp/documentary-proof.mp4
```

Choose a new output filename on subsequent runs. The command produces a 15.5s
four-scene 9:16 video, a storyboard, and an asset/measurement manifest beside it.
The default proof uses original procedural illustrations, explicitly labeled in
the video, and authored synthetic demo narration from the already-installed
FFmpeg/CMU Flite `slt` voice. This is **not** a recording of a customer, a voice clone,
a stock-footage claim or a claim that web research ran. Production rendering only
preserves the voice of its supplied source; synthesis is confined to demo input
generation. Flite is not a new application dependency or paid service.

The synthetic source generator is development-only and refuses required-sandbox
worker mode. The composition engine itself uses the existing native isolation
settings. This cloud host does not support strict Landlock acceptance; do not
claim protected-host/VPS acceptance from its development proof.

With approved public-source access, the same demo can exercise real retrieval:

```bash
.venv/bin/python scripts/demo_documentary.py \
  --allow-public-search --topic 'Apollo 11 Moon' \
  --output /tmp/documentary-public-assets.mp4
```

Required hosts are `commons.wikimedia.org`, `upload.wikimedia.org` and
`en.wikipedia.org`. The flag explicitly authorizes public-topic queries. If
research or rights validation fails, this mode fails closed; it does not silently
substitute illustrations or report research success. Video inserts are used only
when an eligible bounded WebM is available; otherwise a second eligible image is
used. Source metadata/claims and final relevance still require quality review.

## Acceptance and further work

The local rendered proof and synthetic tests verify scene assembly, visual motion,
original voice continuity, image/video support, frame limits, rights records and
failure cleanup. Mocked provider tests verify consent, source hosts, redirects,
rights exclusions, immutable download receipts and query privacy. They do not
prove live provider availability, factual accuracy or documentary quality.

Next integration is the actual automatic flow: source understanding → researched
storyboard with claim/source provenance → relevance/rights filtering → this scene
engine → QA → app playback. Ordinary users should approve the selected research
mode once and receive a finished Short, with storyboard adjustments optional.
No manual image gathering or sentence marking is the intended product workflow.
