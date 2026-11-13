# Quick Review — fewer taps, unchanged source trust

This mobile-only improvement puts already saved clip candidates above the
detailed transcript word editor. Longer recordings (>40 recognized words)
show a compact reading passage with optional full text and optional
individual ending toggles. Existing short transcripts keep their word controls.

## Draft sentence-end cues

The **Draft N sentence endings** action uses only the validated existing
owner-scoped English transcript. It suggests numbered word boundaries from
terminal punctuation, a gap of at least 900 ms before the next word, and the
final word of the recording. A cautious abbreviation list avoids some false
positives (for example `Dr.`), but does not eliminate them.

- The cues are **unverified**. A pause is not proof of sentence completion;
  punctuation and word timing are estimates from speech recognition.
- A draft does not rewrite words, claim verified captions, confirm low-confidence
  words or choose a candidate. It changes only unsaved UI marks.
- Replacing existing marks requires confirmation. All changes invalidate the
  previous acknowledgement and hide stale candidates until explicitly saved.
- The existing human acknowledgement remains mandatory; recording playback
  remains the authority. Only confirmed low-confidence words may be marked
  confirmed, and only by the owner after listening.
- A missing transcript, another account, or an outdated review cannot save
  or render. Existing API version/fingerprints, idempotency, source identity,
  job caps, FFmpeg security, private HTTPS, and the 60-second limit remain
  unchanged.
- A long transcript's word-by-word controls are collapsed for readability,
  never deleted. **Edit individual word endings** reveals every word when needed.

## Device acceptance

1. Open a saved reviewed source with at least two candidates. Verify the first
   suggested option appears before the word editor; examine it first. Change
   options only if desired. Changing selection must not issue render requests.
2. Open an unreviewed English source with 100+ words. The compact transcript
   must show, with a clearly labeled full-transcript view and detailed editor.
3. Apply draft boundary cues once. Check marks against video speech. Toggle
   a wrong cue manually. Verify the acknowledgement is cleared and the clip
   suggestions stay hidden until save.
4. Confirm only words actually heard in playback. Verify unchanged
   original-source identity, owner-scoped saving and revision conflict fencing.
5. Save, choose one candidate, Polish if needed, render once, then compare
   captions, subject framing, audio, duration and Save/Share.
6. Verify no exposure of recordings to outside services and no network call
   for local draft generation.

This is not automatic semantic editing, AI summarization, video understanding
or a guarantee of a ready-to-publish Short. It minimizes repetitive taps while
leaving meaningful review and final playback with the owner.

## Release

No backend change or migration is needed for this increment. After CI and
approval, update only the mobile bundle against the **already deployed**
owner-allowlisted VPS, retaining the private `EXPO_PUBLIC_API_URL` and
`EXPO_PUBLIC_ENGLISH_REVIEW=true` settings. Do not run the VPS updater for
this mobile-only change, and do not change exposure or billing.
