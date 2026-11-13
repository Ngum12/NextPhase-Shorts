# Private English polished-video package

One workspace combines portrait framing, manual caption correction, caption
appearance, bounded voice-volume leveling and a reusable local preset. It uses
the original voice and existing private render queue. It does not add automatic
ASR, semantic rewriting, face tracking, noise removal, music or a public rollout.

## Owner workflow

1. Open the original English project → Review English clips → Refresh review.
2. Select a saved suggestion → **Polish selected clip**.
3. Choose fit/centered fill, or opt-in left/right fill when advertised; captions
   on/off; standard/large text; white/yellow;
   lower/middle placement; original/leveled voice volume.
4. Optionally open the caption editor. Correct text and start/end seconds for
   each existing phrase, comparing against the recording. Confirm that comparison.
5. Save/use **My preset** for appearance, framing, caption on/off and voice choices.
6. **Render polished preview** → confirm → wait → **Watch preview**. Check wording,
   speech alignment, edge details, readability and sound before Save/Share.

Manual **Fill portrait (left/right)** anchors crop in the original video space
before scaling. This helps keep an off-center subject visible in wide sources;
it is not motion tracking, face detection or automatic composition. Portrait
sources may have little or no horizontal room to change the crop. The default
Fit/Center choices remain unchanged; older servers do not advertise
`manual_crop_focus_supported:true`, so the mobile polish screen hides left and
right. Revalidated older-server presets and requests fall back to Center if
a previously selected left/right anchor is no longer supported. Source media,
transcript timings, caption plan, queue and 60-second cap remain unchanged.
Always watch both output edges and compare the selected subject to the source.

Caption edits change only the preview's caption copy. The original recognized
words, scores, word timestamps, review and recording remain unchanged. Timing is
estimated until manually checked. Phrases retain the prepared count (<=80); each
is limited to two 26-character lines, positive ordered non-overlapping times and
the actual frame-derived clip duration. Long text needs shortening/correcting;
the tool does not summarize it. Caption position is fixed, not face-aware.

Optional **Gentle audio fades (80 ms)** taper the first/last 80 milliseconds of
an excerpt's original audio at its source-bound cut points, after optional
leveling. They do not change source video, words, pitch, framing, captions, clip
duration or insert music. No fade is applied by default, so existing presets,
requests and renders retain their original audio behavior. The phone offers
this choice only when the backend advertises `soft_audio_edges_supported:true`.
Legacy device presets without the new field load with original edges; soft
settings are not sent to older servers. Audition real dialogue at both cut
boundaries: source timing can vary and a fade may hide the start of a word. This
is a small boundary treatment, not crossfade, noise removal or source repair.

Voice leveling is one-pass bounded dynamic normalization (maximum 4x gain) and
a peak limiter, not voice synthesis, denoising or a guaranteed integrated-LUFS
target. It may increase background noise. It applies only when audio exists and
retains source pitch/time. Lossy AAC encoding remains. Keep original volume when
the adjusted result is unsuitable.

## Drafts, presets and retries

Draft caption text/times stay in the open editor's memory. Navigation removal
warns about dirty edits; same-owner access-token refresh revalidates ownership and
preserves the workspace. Another account cannot reveal that draft. OS/process
termination still loses unrendered edits; this is not background draft sync.
Confirmed render requests snapshot corrections/settings in the job on the server.

One SecureStore preset per validated account stores only six small choices, not
caption text/times/media/tokens. It is local to that device, not account-wide sync;
account deletion does not remotely erase earlier device metadata. Five recent
render-intent fingerprints/UUIDs per source recover lost acknowledgements without
storing caption text. Changed settings/edits get separate identities; retrying
retained identical settings recovers the same child. More than five historical
variants can retire older local intent keys. Deleting a source clears local intent
metadata and server children through the existing deletion fences.

## Server contract

GET `/api/v1/jobs/{id}/analysis/captions?revision=…&candidate_number=…` returns a
private, no-store draft only for the allowlisted owner and saved current review.
The existing preview POST adds optional closed `polish` settings and optional
`caption_edits` plus strict `acknowledged_caption_edits:true`. No font, raw filter,
path, provider or command is accepted. Cue count/duration/order/layout are checked
against the selected source-bound candidate. Editing does not claim verified
meaning, speech transcription correctness or legal rights.

Settings and edit data participate in idempotency and immutable excerpt specs.
Old preview payloads/hashes/specs retain defaults. Schema remains 0022; API/worker
images must match. Corrected text stays outside FFmpeg grammar in private UTF-8
files with expansion disabled. Exact read grants, credential reduction, process/
network limits, output size/frame/duration QA, leases, quotas and deletion fences
remain. Specs/backups contain caption corrections; exported videos cannot be
recalled. Preset/render features remain restricted to development/test owners.

## Deployment and acceptance for manual horizontal reframing

This feature changes the API/worker renderer and therefore requires the
existing backup-first VPS updater after merging and verifying CI. Preserve
volumes, certificate state, the current owner allowlist, and backup verification.
Do not deploy directly from a feature branch. The UI offers the new choices
only after the new server advertises its capability. Test a landscape source
with a person clearly to the left, and another to the right. Compare Fit,
Center, Left and Right, confirm that 1080x1920/30fps output duration, captions,
original voice, safe output bounds and Save/Share are intact. Also check one
portrait clip (horizontal selection may have no visible effect). Automated
band-color pixel checks prove geometry only, not human quality or gaze tracking.

## Deployment gate and acceptance for gentle audio cuts

This increment changes the protected FFmpeg renderer, so unlike the earlier
mobile-only timeline/checkpoints it **must not be treated as deployed** until
the VPS backup-first updater completes with a fresh authenticated and offsite-
verified backup. The owner's Google Drive quota is currently too small for the
new 788-MiB archive; restore backup capacity before applying this increment.
Do not bypass the backup gate or enable the new option with an old server.

After the VPS update, refresh the phone bundle and compare original versus
Gentle audio fades using a reviewed clip whose cuts occur away from source time
zero. Test both speech starting at the boundary and speech near the ending,
including a no-audio source. Verify frame count, voice pitch, captions,
output duration and no unexpected clipping or added silence. Test Original
volume and Level voice volume independently. Synthetic FFmpeg RMS checks
are not human listening or real-device proof.

## One combined deployment

After merge, close the phone app and keep the VPS SSH window open:

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
.venv/bin/python scripts/update_private_vps.py --apply
```

The updater requires a clean main checkout matching origin/main, obtains a fresh
authenticated offsite backup before building, verifies host containment, preserves
the observed writer selection (including mail only if running), checks an idle
queue, migrates explicitly and recreates matching services. It checks schema/font
and restores previously active timers on success or failure, including handled
interruptions. It never deletes volumes/keys or attempts blind database rollback.
A hard kill/host loss can prevent cleanup. JSON failures report the failed step,
whether writers may be stopped, and timer-restoration errors; stop and investigate
those before retrying or resuming mismatched images. Actual live deployment of
this new helper remains an owner acceptance step. Build/download stdout is
captured by existing maintenance helpers; progress prints phase names.

Then pull mobile code, run `npm ci`, retain the existing private HTTPS URL and
English-review flag, and restart Metro with a clear cache. No new native package
was added. Real phone/VPS audio/caption/framing acceptance is still required.

Synthetic reproducible proof (new output directory only):

```bash
.venv/bin/python scripts/smoke_polished_video.py
```

It generates before/polished videos, a comparison PNG and actual volume/render
measurements from synthetic geometry/tone/manual text. It is not a speech-quality,
human-framing, timing-editor/device or production-performance benchmark.
