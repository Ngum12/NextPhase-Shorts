# Experimental local transcript and excerpt-planning pilot

This is isolated preparation for the owner's requested next app milestone. It is
**not deployed**, is not an API/mobile feature and does not close the remaining
Phase 2/public-release gates. The running worker still performs baseline renders.
No AI, caption/style engine, customer billing or external speech API is activated.

## What can be exercised now

- Strict English/French transcript contracts with source SHA-256, bounded word
  timestamps, token-probability provenance and explicit manual/model labeling.
- Candidate windows that preserve source order and punctuation-complete sentence
  boundaries, reject long gaps and low known probabilities, and stay inside the
  source and requested 5–60-second cap. Output is 1080×1920/30-fps planning data;
  frame duration floors the interval and cannot exceed 60 seconds.
- A private interactive review page with excerpt highlighting and export of the
  selected data-only proposed EDL. Text cannot become HTML/script, no CDN/network
  calls are needed, and a CSP restricts execution to the fixed review script.
- A local Whisper.cpp adapter: file-only 16-kHz mono extraction, explicit engine/
  model SHA-256 checks, CPU-only arguments, bounded native child lifetime/CPU/
  address-space/file size, credential-reduced environment, private temporary
  files and timeout cleanup. It performs no download and never translates speech.

The planner ranks **timing, probability and speech density**, not verified
meaning, virality, a narrative hook or storytelling quality. Token probability
is not calibrated transcription accuracy. Timestamps are operator supplied or
model token estimates; source-video review remains mandatory. Abbreviations,
speaker/context boundaries, missing punctuation and recognition errors require
review; no complete fitting window means no proposed edit rather than fabricated
speech, padding or a cut through an unfinished sentence. Silence/scene detection,
diarization, actual semantic ranking and model quality benchmarks remain pending.

## Reproducible fixture demo — no model or speech API

From the existing checkout and installed backend development environment:

```bash
.venv/bin/python scripts/smoke_analysis.py
```

On Windows use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.
The demo generates original synthetic test video/a sine tone and original manual
English/French annotations. **The spoken content is not recognized from the
tone.** It creates a new ignored private `.data/analysis-demo-<uuid>/` directory:

- `en/review.html`, `fr/review.html`: interactive local review.
- `transcript.json`, `proposal.json`, `proposed-edl.json` inside each language folder.
- `report.json`: explicit `live_asr_tested:false`, candidate counts and provenance.

Open the review page locally. If browser policy blocks file URLs, use a trusted
local HTTP server bound to loopback and the single synthetic demo folder; do not
publish the transcript directory. The page does not upload data or render media.
Its downloaded proposed EDL has `render_supported:false` and cannot be supplied
to the baseline renderer. Renderer integration is a later reviewed change.

## Analyze an operator-owned consented source with manual annotations

Use a new private output folder, never the live worker's media tree. Input must
be a regular local MP4/MOV/WebM accepted by the existing video profile, <=300 MiB
and <=10 minutes. Imports must label themselves `provider:"manual"` and
`timestamp_quality:"operator_supplied"`, exactly match the actual source SHA-256/
probed duration in milliseconds, and use ordered nonoverlapping words.

```bash
.venv/bin/python scripts/analyze_short.py \
  --source /private/consented-copy.mp4 --transcript /private/manual-transcript.json \
  --output /private/new-analysis --requested-seconds 30 --consent-to-local-analysis
```

The fixture demo shows the contract. All models forbid extra fields; words are
bounded to 5,000 and JSON input to 2 MiB. Source hash is rechecked before publishing
output. Output files are mode 0600 in a new mode-0700 directory. Existing outputs
are refused, input files remain intact, and a failed new output is removed.
Errors print fixed codes rather than transcript text, provider diagnostics or
customer paths. Reports contain transcript text: apply consent/retention/deletion
to them explicitly. They are not covered by the live app's media cleanup.
For a failed run, `--diagnostic` adds only error class, fixed reason codes and
validation-type names; it never prints raw model output or transcript values.

### Replan a saved transcript

To try the planner again without decoding video or rerunning speech recognition:

```bash
.venv/bin/python scripts/analyze_short.py \
  --replan-transcript /private/previous-analysis/transcript.json \
  --output /private/new-proposal --requested-seconds 15 --consent-to-local-analysis
```

This validates a bounded (8-MiB maximum) saved transcript, preserves its source
identity, language, words, confidence/timestamps and manual/model provenance, and
creates new private artifacts. It reports `replanned_existing_transcript:true`
and `asr_executed:false`. It does not reread/revalidate the original media; human
review and source-identity checking before future rendering remain required.
Existing files are refused and inputs are preserved. No model/manual-import
options can be combined with this mode.

Planner `sentence-window-v2` checks every sentence start, chooses complete
endpoints before the next low-confidence word or long gap, and uses prefix
statistics to bound scoring work. It retains the 0.45 probability exclusion,
five-second minimum/full-frame and source/requested-duration limits. A weak late
sentence can be excluded while earlier clean complete sentences remain eligible.
This is a timing/probability heuristic, not semantic-storytelling acceptance.

## Optional native ASR — not yet accepted for rollout

Actual weights could **not** be fetched in the cloud workspace: its outbound
policy denies the Hugging Face model host. The pinned native engine built and its
CLI flags were checked. The owner subsequently downloaded upstream-digest-verified
multilingual tiny/base models on the VPS and ran generated English speech through
the adapter. Tiny produced clear recognition errors; base improved the text but
retained a brand-name variation and one below-threshold token. Real natural-speech
English/French quality and actual performance acceptance remain **unverified**.
Executable fixtures verify protocol, credential stripping and timeouts; they are
not ASR evidence. No model files are committed or bundled.

The optional engine tested for compilation is upstream Whisper.cpp **v1.7.6**,
commit **a8d002cfd879315632a579e73f0148d06959de36** (MIT). Build in an ignored private
directory on a Linux development host. No GPU is needed; limit compilation to two
jobs. CMake 3.31.6 was installed as a local build tool, not a runtime dependency:

```bash
git clone --depth 1 --branch v1.7.6 https://github.com/ggml-org/whisper.cpp.git .data/whisper.cpp
git -C .data/whisper.cpp rev-parse HEAD
# Require the exact commit above before building.
cmake -S .data/whisper.cpp -B .data/whisper.cpp/build \
  -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DGGML_CUDA=OFF \
  -DWHISPER_CURL=OFF -DWHISPER_BUILD_TESTS=OFF
cmake --build .data/whisper.cpp/build --target whisper-cli --parallel 2
```

Obtain a multilingual tiny/base GGML model from the official upstream model
source only when network policy permits it. Preserve HTTPS verification and
check its upstream published digest using the pinned `models/README.md`; then
record its SHA-256. The pinned upstream table lists multilingual tiny SHA-1
`bd577a113a864445d4c299885e0cb97d4ba92b5f`. Do not substitute `.en` weights for
French, accept an unverified mirror, or change an expected hash to make a file pass.
Trusted artifact origin is a separate requirement from computing a local digest.
Retain the engine's trusted build directory/shared libraries and applicable
notices; a checksum of one executable is not a full native dependency audit.

Explicit operator invocation after obtaining/reviewing those artifacts:

```bash
.venv/bin/python scripts/analyze_short.py \
  --source /private/consented-copy.mp4 --language fr \
  --engine /private/whisper-cli --engine-sha256 TRUSTED_ENGINE_SHA256 \
  --model /private/ggml-tiny.bin --model-sha256 TRUSTED_MODEL_SHA256 \
  --output /private/new-asr-review --requested-seconds 30 --consent-to-local-analysis
```

Only Linux development/test mode is supported for ASR. Required worker-sandbox
mode refuses execution: native process limits are **not** the production worker's
Landlock/network/tenant boundary. Do not disable that worker guard to try this.
The API and render worker do not import/invoke this path, and the mobile app
does not process audio/video. Production async analysis, leases/cancellation,
private artifact admission/retention and ownership need their own integration.

## Evidence and next gate

Tests cover hostile/nonfinite/overlapping timestamps, hard caps, no-speech/
incomplete/low-confidence results, BPE fragments and French text, source binding,
private permissions, existing-output preservation, credential removal and actual
FFmpeg extraction. Synthetic/manual demos and browser selection/download were
tested in both languages without external requests or JavaScript errors.

Before enabling real inference: acquire trusted weights, measure real consented
English/French examples (including silence, accents and multiple speakers),
review failures and cost/memory on the actual 4-vCPU/8-GB host, implement the
required analysis-worker containment/admission/cancellation/artifact ownership,
and resolve the applicable Phase 2 acceptance gates. No speed, ASR accuracy,
semantic editing or production-readiness claim follows from these fixture checks.
