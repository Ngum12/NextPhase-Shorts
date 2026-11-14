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
3. Tap **Create suggested Short** and confirm **Render draft**. The server selects
   the range automatically; sentence marks and individual word confirmations are
   not prerequisites. Watch the finished clip before Save/Share. **Other clip
   suggestions** and **Review or adjust transcript (optional)** remain available.
   See [automatic clip drafts](AUTOMATIC_CLIP_DRAFTS.md) for selection and bounds.

English only, local accepted uploads, at most three minutes, 1,000 words and
256 KiB of canonical transcript. Longer videos still get the baseline render;
transcription is skipped. No audio/invalid recognition fails without deleting
video. The automatic selector can use sparse-punctuation transcripts without
mandatory human sentence marks; some recordings may still have no usable window.
No verified semantic ranking,
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
all words inside the source and nonoverlapping; this interval repair moves no endpoint by more than
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
| `ASR_OFFSETS_OUT_OF_SOURCE` | Source offsets cannot satisfy the bounds or the terminal correction policy below. |
| `ASR_WORD_ORDER_BACKWARD` | Word starts move backward, or a merged token precedes its word start. |
| `ASR_WORD_OVERLAP_EXCESSIVE` | A positive word overlaps the preceding extent by more than 20 ms. |
| `ASR_TIMING_REPAIR_EXCEEDED` | The bounded repair cannot produce valid intervals within the recording and the existing 20-ms endpoint allowance. |

Classification follows validation order: missing/invalid offsets and unsupported
source bounds are checked before word assembly; final-word eligibility is checked
through assembly, backward starts before excessive overlap, and interval-repair
feasibility last. These codes report the first rejection, not all defects
or the cause of speech-engine estimation errors. Legacy
`ASR_WORD_TIMING_REJECTED` statuses retain their generic explanation; saved
failures are not reclassified. Mobile explains each category, preserves the
original-video/save/share guidance, and requires explicit confirmation to retry.
No transcript text, raw ASR output, offset values or exception details enter
diagnostic statuses or logs. Existing decoder isolation, deadlines, file bounds,
source duration and final strict transcript validation remain unchanged.

## Small terminal word-end overrun correction — 2026-11-14

Owner diagnostics identified a token estimated at 29,880–30,040 ms in a
29,905-ms recording. Strict token validation rejected its 135-ms end overrun
before word assembly. The remaining 29,880–29,905 interval is 25 ms long and
passes the existing positive-duration Word contract; the recording need not be
extended or its speech discarded. This is an estimate correction, not proof of
the true spoken boundary or measured alignment.

The parser now permits only the **final assembled word** to have small token-end
overruns. Each affected token must start strictly inside the real recording;
negative starts, invalid/reversed offsets and starts at/after the source end
remain rejected. Sum all original token-end overruns across the final word's
pieces: the total must be **at most 200 ms**, not 200 ms per piece. This fixed
per-transcript budget cannot be replenished by starting another word or segment.
An overrun followed by another spoken word is rejected. A token starting exactly
at the source end cannot participate in a corrected word, even if zero-width.
In-bounds zero-width words otherwise retain their existing bounded repair.

Only that final word's end is capped to the actual source duration, after token
assembly and existing token-order checks. Original text/order/confidence and
source identity/duration remain unchanged. The separate 20-ms per-endpoint
overlap/zero-width repair then runs unchanged, followed by the strict canonical
Word/Transcript validators. No words are dropped or fabricated. Unrepairable
source offsets retain `ASR_OFFSETS_OUT_OF_SOURCE`; backward/overlap/20-ms repair
failures retain their existing specific codes. The 200-ms budget does not permit
shifting all timestamps, repairing earlier words or accepting new overlaps.

Corrected transcripts reuse `model_token_estimate_adjusted` and proposals carry
`adjusted_word_timestamps`. The review screen explicitly asks the owner to compare
word timings, cuts and captions with playback. No automatic review approval is
added. Valid, unadjusted transcript serialization/fingerprints remain unchanged;
saved successful analyses/reviews are not rewritten. No sandbox, decoder cap,
deadline, source-integrity, owner, cancellation, claim/lease/deletion fence or
private logging rule is changed. No dependency, model or schema change is needed.

### Owner deployment and recovery of an existing failed project

After this change is merged, close the phone app and let active jobs finish.
In the VPS SSH terminal, use the existing backup-first updater:

```bash
cd ~/NextPhase-Shorts
git switch main
git pull --ff-only origin main
sudo -v
.venv/bin/python scripts/update_private_vps.py --apply
```

Continue only after it reports `ok: true`. It retains the current model/settings,
checks the fresh backup and host, rebuilds matching images and restarts services.
Do not hot-patch the worker or delete a project/volume. The agent does not execute
this deployment.

Pull merged `main` in the existing Windows mobile checkout and reload its usual
Expo Go/USB workflow for the generalized playback-review warning. Keep the
existing HTTPS API URL, SDK-compatible client and English-review setting; no
new dependency installation/native rebuild is required by this change.

Open the **original source project** whose English analysis failed. Its basic
Short may still show SUCCEEDED. Tap **Retry timing analysis (experimental)**
(or **Retry English analysis** on an older client) and confirm. The supported
retry uses the retained completed upload and creates a new analysis task with a
stable retry key; it does not re-upload, delete the project or rewrite the old
failure. A lost reply recovers the same new task. The source recording must still
exist and the English pilot must remain enabled/allowlisted, with queue/storage
capacity available. If the original upload has been removed, this fix cannot
recreate it. Do not use **Save & finish (delete project)** for recovery.

On success, open **Review English clips** and compare the final word, captions
and proposed cut boundaries against the recording before saving a review or
rendering a selected clip. Existing successful analyses and saved reviews are
preserved and are not silently re-transcribed by a retry. Other invalid offsets
or conflicting word estimates can still fail safely. Real protected-VPS inference
on the owner's recording and physical-phone acceptance remain owner checks;
synthetic executable fixtures are not speech-recognition quality evidence.

Owner acceptance update (2026-11-14): the owner supplied an `ok: true` VPS
updater result for `7b7bb00`, reported successful analysis recovery, then
confirmed transcript review, polished rendering and phone saving worked. This
verifies that owner-reported private workflow on the tested recording; it is not
an independent ASR-quality benchmark, device matrix or public-release approval.
