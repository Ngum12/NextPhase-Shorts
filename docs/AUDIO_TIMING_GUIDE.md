# Audio timing and quiet-passage guide — private English pilot

New automatic analyses preserve delayed audio on the normalized source timeline
and add bounded quiet-passage evidence to transcript review. The original media,
final voice processing, stored old transcripts and rendered clips are unchanged.

## Concrete timing correction

Previously an AAC track starting two seconds after the video could become a WAV
whose voice started at zero. Its ASR word estimates could consequently precede
the recording by two seconds. Audio extraction now uses a fixed 16-kHz resampler
with `async=1:first_pts=0`, keeping that leading gap on FFmpeg's normalized input
clock. A fixed sample trim and duration/file guards cap analysis audio to the
accepted source duration. This affects analysis PCM, not the original footage.
Existing model word times remain estimates; the zero-duration repair and manual
word/sentence/caption/cut checks remain in place. This is not forced alignment.

An original six-second synthetic video with AAC beginning at two seconds proved
the correction: before extraction had 65,536 samples and first-second mean-square
energy 7,751,944.19; aligned extraction has 96,000 samples and zero energy in the
first second. Quiet analysis found source interval 0–2 seconds. The source hash
was unchanged. These tone/test-pattern results are timing proof, not ASR accuracy
or real-speaker acceptance. Evidence is outside Git in
`/workspace/artifacts/audio-timing/`.

## What pause evidence means

The worker scans its normalized mono 16-bit PCM in 20-ms windows. Runs at or below
-40 dBFS mean-square energy lasting at least 500 ms become quiet intervals. Integer
arithmetic bounds memory and avoids platform floating-point differences. The
scanner reads at most three minutes and checks cancellation at entry, exit and
bounded wall-time intervals. It does not run on phones or load a new model.

This measures low energy, not speech activity, sentence meaning or speaker
identity. Quiet speech can be marked, and music/background noise can hide pauses.
The metadata does not remove audio, move words, rank options or select cuts.
There is no automatic publication or semantic approval.

The phone review guide shows checked audio duration and the first five quiet
passages. For a selected option it reports intersecting quiet duration and warns
if audio timing covers only part of that option. Nearby word context and all
existing manual review/polish controls remain. Snippets and guide calculations
stay in memory; there is no new phone audio processing or persistent transcript
storage. New clients tolerate absent metadata from older servers/analyses.

## Storage, binding and lifecycle

Migration **0024_audio_timing** adds nullable `project_analyses.audio_timing_json`.
Each optional closed record is <=32 KiB, contains source SHA-256/duration, checked
PCM duration, fixed method/alignment settings and at most 360 ordered in-range
quiet intervals. No audio samples or arbitrary text are persisted in this field.
Storage admission reserves additional bounded metadata space.

Worker publication validates timing against the same accepted source/transcript
and uses existing owner/claim/lease/deletion fences. Existing analyses win races
and idempotent imports preserve stored reviews and timing metadata. Owner-only
review routes revalidate source binding; malformed or foreign timing is refused.
API responses retain private/no-store headers. Project/account deletion and
restore tombstones remove the containing analysis row; encrypted DB backups carry
its normal historical custody/retention rules. PCM remains attempt-private and
is cleaned on success/failure/cancellation, with existing cleanup for crashes.
Fixed observation stage `audio_timing` records timing only; samples and transcript
text are not added to general logs.

Old rows retain NULL timing and exactly their existing transcript/review/plan
identities. They are not silently backfilled or re-transcribed. A new automatic
analysis is needed to observe the improved audio clock and guide. No new model,
provider, credentials, permissions or native dependency is introduced.

## One combined deployment and phone check

After merge, use the existing backup-first updater in the VPS SSH window:

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
sudo -v
.venv/bin/python scripts/update_private_vps.py --apply
```

It takes a verified offsite backup, requires an idle queue, builds matching images,
migrates the new nullable column, restarts the existing writers and restores
timers. Do not start new images against the old schema or improvise a downgrade;
use the matching-code recovery process if needed. The existing model and private
review owner flags remain in place.

Pull the Windows mobile checkout and reload Expo Go using the current USB/8082
workflow. No npm dependency installation or new native build is needed. Use one
new consented English recording under three minutes with a brief natural pause,
opt into English analysis and open its transcript review. Check the guide against
playback, then review/choose/polish/render as before. Existing projects keep working
with their previous timing; they do not need bulk re-uploading.

## Verification scope

Tests cover actual delayed AAC extraction, unchanged source hashes, low-energy
threshold edges, minimum run lengths, endpoints, signed PCM extremes, cancellation,
truncation/profile/duration refusal, bounded source-matched metadata, owner-only
read/deletion, idempotent preservation, optional legacy rows and migration. The
existing real-MP4/FFmpeg/executable-fixture worker pipeline now publishes timing
alongside its validated transcript and cleans private scratch. Mobile tests cover
legacy absence, invalid/foreign metadata rejection and the bounded guide.

TypeScript/Android export and full backend/mobile regressions are run before
merge. Actual speech accuracy, protected-host behavior of the new filter and
physical-phone acceptance remain live checks after deployment. No real recording,
new external provider call or paid service is used in managed-cloud testing.
