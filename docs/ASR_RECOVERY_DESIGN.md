# English ASR reliability — release-blocking recovery design

The private trial has failed on multiple legitimate recordings with
`ASR_WORD_TIMING_REJECTED`. **This is a system reliability problem; do not
tell customers to keep retrying the same file.** Track implementation and
release gate at [issue #64](https://github.com/Ngum12/NextPhase-Shorts/issues/64).

## What is actually deployed?

- Pinned CPU `whisper.cpp v1.7.6` CLI, `-ojf`, one multilingual
  `ggml-base.bin` model, no other ASR provider.
- `local_transcription.parse_whisper` turns token offsets into word ranges.
  Every token offset must be within the source, each word must occupy
  positive time, and word ranges must be ordered/nonoverlapping. Zero-width
  word estimates can be adjusted by at most 20 ms. Large overlaps, broken
  ordering, out-of-range timestamps or unrepairable zero-width tokens reject
  the attempt; one invalid word can discard all otherwise useful transcript.
- `contained_asr.transcribe` maps that situation to the privacy-safe
  `ASR_WORD_TIMING_REJECTED` status, deletes attempt-private inference
  JSON, and leaves the original video intact. This category does **not**
  disclose which rule the customer's media tripped.
- The existing `worker_asrcheck` validates artifact SHA and worker
  sandbox availability, **not** transcription accuracy on real speech.
  There is no real-audio accuracy benchmark to support a production claim.

## Immediate UX mitigation (this PR; not an ASR fix)

For timing failures, explain that automatic clip suggestions are currently
unavailable, the root is the editor's timestamp pipeline, the same file may
fail again, and that an already completed baseline Short may still be
saved/shared. Keep a voluntary retry but stop presenting it as an assured fix.
No backend, artifacts, media, secrets, database, deployment, CPU or worker
settings are changed. This is **not** release readiness.

## Required recovery architecture (follow-up PRs)

1. **Capture bounded failure reasons with no media payload.**
   Count only enumerated categories: invalid/missing/out-of-bounds token
   offsets; nonmonotonic or overlapping words; zero-width correction beyond
   limit; transcript text/protocol inconsistency. Do not log token text,
   private customer audio, project titles/paths, or per-word times.
   Aggregate operational telemetry only under controlled access.
2. **Recognize first, align second.** Treat transcription text and usable
   segment-level times as separate from fine-grained word alignment. If word
   timing fails, present a validated transcript for private human review
   with its explicit low-precision/unknown-timing status rather than
   discarding it. This requires a versioned storage and API contract; never
   label interpolated words as acoustically verified.
3. **Independent aligned fallback**, with verified offline artifacts.
   Benchmark (a) the existing Whisper.cpp base configuration,
   (b) `faster-whisper` with a sensible CPU `int8` model for ASR, and
   (c) WhisperX / a separately vetted CTC forced aligner for word boundaries.
   Do not assume the current tiny VPS can run a second model comfortably;
   measure CPU, peak RSS, scratch size, p95 latency, sandbox compatibility,
   and cancel/OOM behavior under concurrent render load. Evaluate *model
   weights* for license/privacy/security, not only code licenses. Choose
   the smallest tested deployment; a larger Whisper model alone does not
   guarantee correct word timestamps.
4. **No-dead-end fallback in the app.** If alignment remains unreliable,
   users should choose source start/end via a manual trim and render through
   an existing owner-authenticated, bounded, idempotent worker. No automatic
   captions when timing is unknown, no fabricated confidence, no silent
   dropping of misaligned speech. Show the original clip and still permit
   saving/sharing the baseline Short.
5. **Quality and rollout gate.** Maintain consented test recordings across
   African English accents, silence, music, multiple speakers, acoustic
   conditions, and source codecs/durations. Collect word-error-rate
   against hand-reviewed references, valid alignment coverage, cut
   accuracy, failure and retry rates, p95 CPU latency/RAM, and user
   completion. Assert genuine audio-boundary tests, not only mocked JSON.
   Preserve <=60 s, source SHA binding, human review, project ownership,
   backup, storage reservation, max attempts, worker sandbox, deletion,
   private error codes and unmodified current VPS until an approved update.

## Useful official references

- https://github.com/SYSTRAN/faster-whisper — CTranslate2 ASR with CPU
  INT8 and optional word timestamps.
- https://github.com/m-bain/whisperX — separate forced alignment, with
  documented limitations for some words and overlapping speech.
- https://github.com/ggml-org/whisper.cpp — configurable local ASR;
  token timestamp estimates are not guaranteed to be correct.

Avoid promising "perfect" transcription or automatically upgrading the
live server from a UI-only fix.
