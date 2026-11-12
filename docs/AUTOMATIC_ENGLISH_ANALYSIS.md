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
