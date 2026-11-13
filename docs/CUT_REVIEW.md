# Phase 3 — Source-bound cut checkpoints

This private editor improvement adds an **Opening checkpoint** and **Ending
checkpoint** next to the existing read-only evidence timeline for a selected
English clip. It helps a person inspect two common polish risks: context that
does not stand alone, and a cut near a measured quiet interval or sampled
visual change. This is **not** semantic judgement, AI quality scoring, or
automatic editing.

## Source, safety and correctness

- Read only an already validated owner-scoped English analysis response.
- Use the selected candidate's original `source_start_ms` and
  `source_end_ms`; never snap or extend these times.
- Use audio and visual evidence only when the source SHA-256 and source duration
  match the transcript's source identity. Otherwise omit those cues.
- Look for the nearest detected quiet interval edge/touch or sampled visual
  change within one second of each boundary. A detected quiet interval is
  an energy estimate, not a linguistic pause. A visual change is an RGB
  sample difference, not a scene understanding model.
- The opening may need context when the first word is one of a small,
  declared list of pronouns or linking words. This is a reminder, not an
  assertion that the clip lacks meaning.
- When a validated optional scan ends before a cut boundary, disclose that
  the relevant evidence was not checked. Missing or unavailable evidence is
  never treated as zero changes or zero quiet passages.
- Show a neutral review prompt if no boundary-adjacent evidence is present.
  No quality score, approval, popularity prediction or render recommendation.
- A transcript review must still be saved before preview or polishing.
  Existing ownership, revision checks, consent, job limits, queue,
  FFmpeg child isolation and original-voice defaults stay intact.
- No new database migration, API, paid provider, secret, model, package,
  phone-side video decoder or background inference.

## Verification

`apps/mobile/tests/cutReview.test.cjs` covers source clock references,
nearby events, tie-breaking, partial coverage, mismatched source identities,
and invalid candidates. `analysisScreen.test.cjs` covers selected-option
integration, dirty-review hiding and no render side effect.

From `apps/mobile` run:

```bash
npm ci
npm run typecheck
npm run test:analysis
```

CI also bundles Android JavaScript and runs mobile checks.

## Required physical-device acceptance (not automatic)

1. Update only the private test app after CI and PR approval.
2. Open a saved English review with at least two clip suggestions; change
   the option and confirm the timeline and both checkpoints follow the
   chosen **source** boundaries.
3. Try a recording with a measured quiet interval near one cut, and another
   with a detected sample-level visual change. Compare against playback;
   do not expect genuine semantic change recognition.
4. Try an unavailable and partially sampled visual guide: it must avoid
   declaring an unchecked interval unchanged.
5. Modify transcript review marks without saving. Verify suggestions and
   checkpoints are hidden until review is saved again.
6. Render both a plain and a polished preview, verify the output duration,
   framing, captions, original audio and selected interval are unchanged
   relative to the existing workflow.
7. Do not activate billing or allow general customer access.

This is separate from diagnosing the owner's 4K source decode latency and
intermittent preview failure on the Contabo VPS. Those remain open gates.
