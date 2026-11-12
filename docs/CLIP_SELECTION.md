# Clearer clip selection — private English pilot

The package improves the existing review workflow: alternatives favor different
source ranges, each option shows its opening words, and the selected option shows
nearby transcript context. This is functional prototype work, not a UI redesign.

## What the user sees

After saving a transcript review, up to five options compare the existing model
word confidence, estimated speech coverage and output duration. The first option
keeps the strongest technical score. Later options also consider how much source
footage they share with already selected options. A list may contain fewer than
five choices; the system does not create filler options to reach five.

Each option shows up to eight opening words (96 characters). The selected option
shows up to eight words before and after its source range (160 characters each),
which alternatives share footage, and how many low-confidence words the user had
confirmed. A fixed English opening-word heuristic can suggest checking earlier
context; it does not alter scores, discard a clip or verify meaning. Nearby words
are excerpts, never an invented summary. Playback remains necessary for audio,
cut, caption and meaning review.

These are local deterministic rules. No language-model/provider call, new model,
paid API, popularity prediction, semantic ranking or automatic meaning approval is
included. Temporal overlap is not semantic similarity; repeated statements in
different parts of a recording can still appear as alternatives. Framing, original
voice, word timings, captions and render bounds retain their existing behavior.

## Selection and revision boundaries

Only human-reviewed proposals use `sentence-window-v4-diverse-reviewed`.
Unreviewed planning keeps its existing v2 behavior and cannot enable rendering.
The pool retains existing complete-sentence, confidence-confirmation, long-gap,
source-time, frame and requested-cap checks. No source interval is modified by
selection. Greedy selection subtracts 0.35 times maximum temporal intersection /
union with prior picks from each existing technical score; pairs with >=0.85
intersection / union are excluded. Stable source-time/word tie-breaks make results
reproducible. At most five passes examine the bounded candidate pool.

New review revisions hash the exact canonical proposal as well as transcript and
human annotations. Changing candidate order/ranges, scores, cap or planner identity
changes that revision. Preview and polish intents therefore cannot reuse an old
option number for a changed selection. Lost-save replies return the persisted
matching review/plan; stale different edits remain refused. Existing rendered
previews and their immutable request-key replays retain their original source
ranges even after a later replan.

Stored legacy v1/v2/v3 proposals and review revisions remain readable and are not
recomputed during GET. Existing reviewed projects switch to the new planner only
when the user explicitly saves their review again. The original transcript and
annotations are preserved. This JSON contract extension needs no database migration.

## One combined update after merge

In the VPS SSH window, close active app work and use the existing updater:

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
sudo -v
.venv/bin/python scripts/update_private_vps.py --apply
```

This keeps the existing fresh verified offsite backup, idle-queue check, matching
images, schema/host/font checks and timer restoration. No keys, settings or model
weights need changing. In Windows PowerShell pull the mobile checkout, then reload
Expo Go (or restart the current localhost Metro on port 8082 with the existing USB
reverse). No dependency installation or native build is added.

On the phone open an existing source → Review English clips → Refresh review →
Save review and find clips, preserving/checking sentence marks and confirmations.
Compare the opening snippets and nearby context, choose an option, then use the
existing polish/render/playback flow. An existing video need not be uploaded or
transcribed again. Alternatives can overlap; this is disclosed rather than hidden.

## Verification scope

Tests cover deterministic/bounded diversity, near-duplicate suppression and other
source regions, intact reviewed sentence/time/cap constraints, legacy hash/read
compatibility, explicit replan/stale fencing, old preview replay and lost-save
recovery. A real synthetic seven-second MP4 fixture renders option 2 from source
seconds 1–6 to a verified five-second vertical output through the existing worker.
This is render/range proof, not real speech or editorial-quality acceptance.

Mobile adapters/components check bounded literal context, source edges, overlaps,
confirmed-word counts, contextual-opening advice, truthful new/legacy labels,
existing account/dirty/retry guards and explicit preview requests. TypeScript and
Android export validate bundling; physical-phone and live-VPS acceptance follow
merge. No new customer text is logged or persisted on the phone; snippets derive
in memory from the already authenticated source-bound transcript.
