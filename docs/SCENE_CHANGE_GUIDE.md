# Sampled visual-change guide — private English pilot

New automatic analyses can show possible visual transitions near reviewed clip
boundaries. It is a Phase 3 analysis foundation, not semantic scene understanding,
speaker tracking, automatic jump cuts or a final interface redesign.

## What changes on the phone

The review screen adds **Visual change guide** after a new automatic analysis.
Available guidance shows the sampled duration and up to five possible-change
timestamps. The selected clip shows how many changes lie inside it and whether
one is within about a second of its start/end. Partial sampled coverage is explicit.
Users still compare the recording, mark sentence endings, confirm words, choose
an option and review the rendered result. Source ranges, scores, voice, captions,
existing plan/review identities and earlier rendered clips are not changed.

An unavailable guide is distinguished from an available guide that found no large
changes. Handled visual-decoder/timeout/profile failures do not discard a valid
transcript; the UI explains that transcript review can continue. Cancellation,
claim loss and storage/worker failures retain the existing job recovery/fencing
rules. An abrupt worker crash is not treated as a successful optional fallback.

## Method, uncertainty and bounds

The protected FFmpeg decoder creates a temporary **64×36 RGB proxy at 2 fps** on
the server, with its sampling clock normalized using `fps start_time=0`. The
parent compares the mean absolute channel difference between adjacent samples.
Differences >=180/1000 become possible changes; nearby detections within one
second keep the strongest sample, with the earlier sample winning a tie.

This is coarse, half-second sampling, not exact shot timing or a learned scene
model. Camera movement, flashes and lighting may trigger detections; gradual,
subtle, color-similar or brief changes can be missed. FPS normalization may repeat
frames across timing gaps; delayed/missing video is not separately diagnosed.
Technical delta values are not probabilities, semantic scores or meaning approval.
No audio, source footage, word timestamps or automatic cuts are changed by it.
No model download, external provider, new dependency or phone-heavy analysis is
introduced. The current private English/local/three-minute profile remains.

The optional decoder has a 60-second wall deadline, a **1-GiB virtual-address
limit**, CPU/process limits, a **3-MiB kernel output-file bound** and existing
required Landlock/seccomp file/network isolation. The memory/file bounds apply
also to native Linux test mode. Unsupported required containment stays closed;
there is no retry without protection. Only one extra decoder runs at a time,
before existing audio/ASR stages. Existing 40-MiB-per-attempt scratch reservations
cover the proxy, PCM and bounded ASR JSON, within the existing analysis hard lease.
Parent pixel comparison streams two tiny frames and polls cancellation.

## Storage, privacy and compatibility

Migration **0025_scene_analysis** adds nullable
`project_analyses.scene_analysis_json`. Closed metadata is <=32 KiB and binds to
the accepted source SHA-256/duration. It stores fixed method/settings, available/
unavailable status, bounded sample coverage and at most 180 ordered numeric
changes. Unavailable results cannot claim successful samples or changes. No image
pixels, text, paths, filters or commands enter this field. Additional bounded DB
metadata space is reserved at admission.

Publication retains owner/claim/lease/deletion/restore fences. Owner-only review
reads revalidate source binding and keep private/no-store headers. Idempotent
imports and races preserve existing reviews and metadata. Project/account deletion
and restore tombstones remove the containing analysis row. Encrypted historical
DB backups keep their existing custody/retention rules.

Proxy pixels stay in a private attempt subdirectory and are removed on normal,
failed or cancelled completion. Crash remnants follow existing attempt cleanup
and encrypted-media backup custody; they are not sent to phones, Git or logs.
Fixed `scene_analysis` observations record stage/resource outcomes without pixel
or transcript payloads. Handled optional failures remain observable as stage errors.

Legacy records retain NULL and are not reanalyzed on read or when resaving a
review. New and older clients tolerate missing metadata. Existing transcripts,
review/plan revisions and rendered outputs remain unchanged. This guide appears
only for **new automatic analyses**, not every pre-existing saved project.

## One combined deployment and acceptance check

After merge, use the normal backup-first updater in the VPS SSH window:

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
sudo -v
.venv/bin/python scripts/update_private_vps.py --apply
```

It verifies a fresh offsite backup, checks the idle queue, builds matching images,
migrates the new nullable column, restarts existing writers and restores timers.
No key/model/config changes are needed. Use matching-code recovery rather than
starting new images against an old schema or improvising a downgrade.

Pull the Windows mobile checkout and reload Expo Go using the current USB/8082
workflow. No dependency install/native rebuild is added. For one phone check,
upload a new consented English recording under three minutes with an obvious
change in viewpoint, opt into English analysis, and compare the visual guide with
playback. A stationary recording may correctly report no large changes. Existing
projects keep working without bulk re-uploading or transcription changes.

## Evidence and remaining acceptance

A real original six-second black→white synthetic MP4 produced twelve samples and
one possible change at source second 3, preserving source hash and removing the
proxy. The evidence input/report live outside Git at
`/workspace/artifacts/scene-analysis/`. This is technical cut-detection proof, not
real-speaker or editorial-quality acceptance.

Tests cover RGB comparison/nearby suppression, hard-cut decoding, sample/time/
metadata bounds, kernel memory/file limits, cancellation versus optional failure,
private source/lifecycle binding, legacy migration and the real MP4/FFmpeg plus
executable-fixture transcription pipeline both with visual guidance and with an
unavailable fallback. Mobile tests cover bounded source-matched metadata,
unavailable/legacy handling, nearby-boundary context and original option integrity.
Full regressions, TypeScript and Android export run before merge. Actual protected
VPS filtering, real scene quality/latency and physical phone acceptance remain
post-merge checks; this managed host lacks required Landlock support. No private
recordings, paid infrastructure or external model services are used here.
