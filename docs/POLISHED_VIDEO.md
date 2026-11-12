# Private English polished-video package

One workspace combines portrait framing, manual caption correction, caption
appearance, bounded voice-volume leveling and a reusable local preset. It uses
the original voice and existing private render queue. It does not add automatic
ASR, semantic rewriting, face tracking, noise removal, music or a public rollout.

## Owner workflow

1. Open the original English project → Review English clips → Refresh review.
2. Select a saved suggestion → **Polish selected clip**.
3. Choose fit/centered fill; captions on/off; standard/large text; white/yellow;
   lower/middle placement; original/leveled voice volume.
4. Optionally open the caption editor. Correct text and start/end seconds for
   each existing phrase, comparing against the recording. Confirm that comparison.
5. Save/use **My preset** for appearance, framing, caption on/off and voice choices.
6. **Render polished preview** → confirm → wait → **Watch preview**. Check wording,
   speech alignment, edge details, readability and sound before Save/Share.

Caption edits change only the preview's caption copy. The original recognized
words, scores, word timestamps, review and recording remain unchanged. Timing is
estimated until manually checked. Phrases retain the prepared count (<=80); each
is limited to two 26-character lines, positive ordered non-overlapping times and
the actual frame-derived clip duration. Long text needs shortening/correcting;
the tool does not summarize it. Caption position is fixed, not face-aware.

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
