# Automatic English Short drafts

The normal private workflow no longer requires marking sentence endings or
confirming individual transcript words before generating a Short. Once English
analysis is ready, **Create suggested Short** prepares the server's first-ranked
option. Confirm **Render draft**, watch the finished clip, and Save or Share.
**Other clip suggestions** and **Review or adjust transcript (optional)** are
available when the owner wants alternatives or detailed corrections.

This is an automatic contiguous-excerpt selector, not a completed semantic AI
director. It does not yet understand a recording's story, verify meaning, join
noncontiguous highlights or implement the six promised style engines. Watching
the result before sharing replaces the mandatory word-by-word preparation;
human playback is still needed to catch incorrect speech estimates and cuts.

## What is selected automatically

The server uses the existing original-word transcript and actual source clock.
It finds punctuation/pause boundaries, compares opening/ending cues, confidence,
speech coverage and duration, and reduces near-duplicate source ranges. A
question with its follow-up is preferred over an isolated question ending;
dependent openings receive a penalty. These are explicit heuristics, not
semantic understanding, virality predictions or verified story-quality scores.

Sparse punctuation no longer leaves the user with an empty sentence-marking
task. The selector also considers clause/short-pause starts and a bounded
half-duration grid; it falls back to original word endpoints when needed.
Fallbacks are disclosed because a word boundary is not proof of a complete
thought. The selector never moves words, pads speech or invents a sentence.
It does not cross gaps longer than two seconds. Windows must remain inside
the real source and the requested cap, between 150 and 1,800 output frames
(5–60 seconds), at 1080×1920/30 fps. A five-second cap may have no valid exact
word-boundary window; it is never padded to force one.

An occasional low-confidence word is no longer a per-word confirmation gate
for a private draft. It remains unchanged and is disclosed as uncertain;
windows with a known mean confidence below .45 are withheld. Scores and words
are never marked human-confirmed automatically. If no usable range fits, the
app offers another recording or optional review rather than claiming success.
No new model, provider, paid integration or dependency is used.

## Existing projects, provenance and safeguards

- Suggestions are computed read-only from an already owner-scoped analysis.
  Existing transcripts, sentence marks, saved reviews, plans and outputs are
  preserved. Older analyzed projects can use the new flow without re-uploading
  or rerunning ASR. Detailed reviewed rendering retains its original gates.
- `GET /api/v1/jobs/{id}/analysis/automatic-clips` returns a fixed-version plan
  with numeric ranges and a digest over the transcript identity, source, current
  analysis revision, requested duration and complete candidate list. The server
  recomputes and checks that digest when rendering or preparing captions; clients
  cannot submit their own source ranges. Review changes fence stale new intents.
- Preview requests explicitly set `automatic_draft: true`; their durable keys
  remain distinct from reviewed requests. A lost reply recovers the same queued
  job, including after a later review change. Listing or comparing suggestions
  never queues multiple renders or charges multiple reservations.
- The immutable worker spec uses `excerpt-auto-1`, a canonical transcript digest
  and a null human-review digest. It never fabricates a human review. Legacy
  `excerpt-1` still requires its human-review digest. No database migration is
  needed; API and worker code must be updated together.
- Existing private English owner allowlisting, accepted-upload checksum/size/
  duration binding, queue/storage admission, decoder guards/resources/deadlines,
  cancellation/lease/deletion/restore fences and output QA remain in force.
  This mode permits a private draft without transcript annotations, not public
  publishing or a production rollout.
- Captions derive from the same unmodified transcript and bounded layout rules.
  If a selected caption layout does not fit, the app offers the same draft
  without captions. Caption edits still require their own explicit recording
  comparison. No transcript, private media, native output or secret is logged.
  Mobile opening/ending snippets stay in memory; render intents store hashes
  and UUIDs, not transcript text.

## One owner update and acceptance check after merge

Use the existing backup-first updater from the VPS's clean merged `main` checkout:

```bash
cd ~/NextPhase-Shorts
git switch main
git pull --ff-only origin main
sudo -v
.venv/bin/python scripts/update_private_vps.py --apply
```

After `ok: true`, pull merged `main` in the existing Windows mobile checkout and
reload its usual Expo Go/USB workflow. Preserve the existing HTTPS API URL and
private English pilot setting. No new model, package install or native rebuild
is introduced. Older servers/clients retain the existing reviewed workflow.

For one focused check, open an existing successfully analyzed original project
and tap **Create suggested Short** → **Render draft**. No sentence or word
confirmation screen should be required. Watch the resulting clip for speech,
cuts, captions, framing and original voice, then **Save without deleting**.
Optional alternatives should render only the chosen option. Existing saved
reviews should remain available unchanged. Actual VPS/phone cut quality and
semantic suitability remain owner acceptance; synthetic fixtures do not prove
recognition accuracy or close the remaining Phase 3 creative-director work.


## Optional content-aware choice

[Create with Gemini](GEMINI_CLIP_SELECTION.md) can select a candidate from this
same bounded shortlist after explicit transcript-sharing consent. The standard
endpoint/selector remains read-only and local; Gemini selection is a separate
explicit POST and cached GET. The model never supplies word timings, native
commands or media. Watch the result; its choice is not semantic-quality proof.
