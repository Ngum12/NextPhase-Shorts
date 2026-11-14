# Automatic English analysis — private pilot

New original recordings can go from phone upload to server transcription and
English suggestions without an operator importing transcript files. This is the
next functional milestone; the current screens remain a prototype.

## Phone flow

1. In Create, opt into **Find English clips after upload**. The upload retains its
   existing baseline render and additionally queues analysis when capacity permits.
   Consent is part of the immutable resumable upload intent, including after an
   interrupted transfer/app restart. Unchecked uploads retain their old behavior.
2. Open the original project. **English clip suggestions** shows waiting, queued,
   processing, failure/retry or a ready transcript. You may leave the screen after
   server acceptance. For an existing accepted upload, **Find English clips** asks
   for server-analysis consent first. Cancel stops analysis, not the baseline job.
3. Open **Review English clips**, compare words and sentence boundaries with the
   recording, confirm uncertain words and save the review. Then choose an option,
   polish, render and play/save/share it through the existing private workflow.

English only, local accepted uploads, at most three minutes, 1,000 words and
256 KiB of canonical transcript. Longer videos still get the baseline render;
transcription is skipped. No audio/invalid recognition fails without deleting
video. A transcript may initially have no complete suggestions: human sentence
boundaries and low-confidence review can still be required. No semantic ranking,
verified meaning, viral-quality guarantee, automatic publication, French rollout,
intelligent subject tracking or final UI redesign is claimed.

## One combined VPS deployment after merge

The existing VPS already has the multilingual base model in
`.data/asr-pilot/ggml-base.bin`. Keep existing owner review settings, private HTTPS,
backups and monitor configuration. From the **VPS SSH window**:

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
.venv/bin/python scripts/update_private_vps.py --apply --enable-english-analysis
```

The updater takes a fresh authenticated/offsite-verified backup, copies that public
model into a read-only mount after checking pinned upstream SHA-1
`465707469ff3a37a2b9b8d8f89f2f99de7299dac`, derives its SHA-256, and writes only
analysis settings into the existing private server.env. It preserves unrelated
secrets and refuses a conflicting existing model. It then builds matching images,
checks worker isolation/model/engine identity before stopping writers, applies
migration **0023_english_analysis**, restarts the previously running writers and
restores timers. A failure reports its phase; do not delete volumes or improvise
schema rollback. Model bootstrap does not download weights or rotate credentials.
Other updates prepare an empty mount without enabling analysis. For a replacement
VPS, provision the same verified public model separately; it is not customer media
and is not included in the encrypted media/database bundle.

In **Windows PowerShell**, update the phone bundle:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull --ff-only origin main
cd apps\mobile
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" reverse tcp:8082 tcp:8082
npx expo start --go --localhost --port 8082 --clear
```

Keep `EXPO_PUBLIC_ENGLISH_REVIEW=true` and the existing HTTPS URL. No new native
dependency, API key or model goes on the phone. Confirm USB authorization if
needed. A 403 from `/ready` means check the existing direct-client IP allowlist;
it is independent of transcription. Use one new consented English recording to
verify transcript, cancel/retry, review, suggestions and a polished playback.
Existing manually reviewed projects remain available and are never overwritten.

## Execution, privacy and failure boundaries

Analysis uses a typed child RenderJob in the existing owner/global bounded queue;
non-video tasks are excluded from My Shorts. Reservations cover source copies and
40 MiB scratch per bounded attempt. Automatic upload requests waiting for capacity
are admitted by a bounded supervisor pass. Terminal failures/cancellations/deleted
children are not automatically restarted. Explicit retries reuse the terminal
attempt UUID as their request key, so a lost reply does not create duplicate work.
No files, filters, commands, tokens or model paths can be supplied through the API.

The worker verifies an attempt-private copy of the accepted SHA-256/duration,
extracts mono 16-kHz PCM, and launches pinned Whisper.cpp v1.7.6 (commit
`a8d002cfd879315632a579e73f0148d06959de36`) with CPU-only portable static ggml/
whisper libraries, two threads, no GPU/CURL/plugin loading, fixed English and full
JSON token estimates. Only the worker Docker target contains the engine. The
public base model is mounted read-only outside customer media. The native child
gets a credential-reduced environment, private precreated JSON output, CPU/file/
memory bounds, a 900-second inference deadline and process-group termination.
Required mode uses the existing Landlock/seccomp filesystem/network boundary with
exact audio/model/engine/output grants. It fails closed on unsupported hosts.
The separate operator CLI remains blocked in a required worker; its guard was not
removed. The protected parent handles database/queue I/O; the decoder has no such
credentials or access. This is process containment, not kernel certification.

Cancellation/claim loss/deletion/restore tombstones prevent publication. Source
and PCM/JSON attempt copies are removed on normal/failed/cancelled exit; existing
cleanup handles crash remnants. Published transcripts/review metadata live in the
existing source-bound ProjectAnalysis record and follow its deletion/backup rules.
Downloaded/exported videos and historical backups have their existing independent
custody/retention limits. Do not paste private transcript dumps into logs.

## Evidence and remaining acceptance

Backend tests cover upload opt-in/replay, pending capacity recovery, owner/private
routes, typed-task migration, cancellation, expired claims/deletion fences, retry,
trusted publication, artifact identity/bootstrap, timeout/process teardown and a
real accepted MP4 → real FFmpeg → executable protocol fixture → private transcript
pipeline. That fixture is not actual speech recognition. Mobile adapter/component
checks cover consent, durable upload intent, lost replies, explicit retries,
ready review routing and stale-session reply/dialog exclusion.

The pinned native engine and Docker worker image compile and the CLI runs with
container restrictions. This managed host lacks the required Landlock support and
cannot fetch the real model under its network policy. Actual protected inference,
English accuracy/latency under VPS load and physical phone acceptance therefore
remain post-merge checks on the operator's existing verified model. These tests do
not constitute public production, ASR quality or commercial/legal clearance.

## Zero-duration word timing repair — 2026-11-12

A protected VPS run decoded the recording and ran the native engine successfully,
but failed when a recognized word had equal start/end model timestamps. The
adapter now preserves every recognized word and its score, and can make minimal
positive intervals for that specific case. A forward/backward boundary pass keeps
all words inside the source and nonoverlapping; no endpoint may move by more than
20 ms (two Whisper timestamp ticks). Adjacent positive-length intervals may
overlap by at most 20 ms, provided every repaired boundary stays within the same
20-ms allowance and words remain ordered. Backward order, excessive adjustment, invalid metadata,
text/control errors or insufficient source time still fail closed. Strict Word
and Transcript contracts continue rejecting zero-length or overlapping intervals.

Adjusted transcripts explicitly use `model_token_estimate_adjusted`; proposals
carry `adjusted_word_timestamps`, and mobile review displays a plain-language
warning to check cuts/captions. This is bounded estimate repair, not forced
alignment, measured word timing or verified meaning. Existing valid transcripts
retain identical serialization/hashes; existing human review is not rewritten.
No speech/audio is edited by this repair.

Timing failures now persist one fixed, content-free owner-visible code:

| Code | Meaning |
| --- | --- |
| `ASR_OFFSETS_MISSING` | A spoken token has no offsets object or lacks an endpoint. |
| `ASR_OFFSETS_INVALID` | Offsets are malformed, endpoints are not integers, or end precedes start. |
| `ASR_OFFSETS_OUT_OF_SOURCE` | An otherwise valid interval extends outside the recording. |
| `ASR_WORD_ORDER_BACKWARD` | Word starts move backward, or a merged token precedes its word start. |
| `ASR_WORD_OVERLAP_EXCESSIVE` | A positive word overlaps the preceding extent by more than 20 ms. |
| `ASR_TIMING_REPAIR_EXCEEDED` | The bounded repair cannot produce valid intervals within the recording and the existing 20-ms endpoint allowance. |

Classification follows validation order: missing/invalid/source bounds are
checked before word assembly, backward starts before excessive overlap, and
repair feasibility last. These codes report the first rejection, not all defects
or the cause of speech-engine estimation errors. Legacy
`ASR_WORD_TIMING_REJECTED` statuses retain their generic explanation; saved
failures are not reclassified. Mobile explains each category, preserves the
original-video/save/share guidance, and requires explicit confirmation to retry.
No transcript text, raw ASR output, offset values or exception details enter
diagnostic statuses or logs. Existing decoder isolation, deadlines, file bounds,
source duration and final strict transcript validation remain unchanged.

After merge, use the usual backup-first updater with `--apply` (no new model,
credentials or database migration). Pull the phone checkout for the additional
review warning. Then tap **Retry English analysis** on the existing source
project; no re-upload or transcript export is needed. Recognition against the
owner's recording remains a live acceptance check after the update.
