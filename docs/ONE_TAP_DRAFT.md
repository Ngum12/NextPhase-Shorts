# One-action polished Short draft (private pilot)

This increment joins **existing** speech analysis, reviewed candidate ranking,
caption preparation, saved appearance choices and private FFmpeg render into a
single, consented action on an already analyzed project.

## Owner journey

1. Upload a consented local recording (within existing source/profile limits)
   and select the server-side English analysis option.
2. Wait for the English transcript to be prepared. On the source project, tap
   **Prepare a Short draft**.
3. If the transcript has not been reviewed yet, the app sends the owner to
   **Review English clips**. The user must compare words and boundaries with
   the original recording and save before any quick draft is allowed.
4. If at least one reviewed candidate exists, the app selects candidate #1
   (the highest-ranked *technical* proposal). It loads the owner's saved
   Polish preset, if any, or uses safe Fit + clean phrase captions + original
   voice defaults. It preflights caption layout without changing text.
5. The app displays the selected duration, appearance, captions/fallback and
   the limits of the ranking. **Render draft** explicitly queues one private
   preview through the existing idempotent authenticated polished-preview API.
6. Watch the output on the private preview project, checking the first and
   last words, cuts, caption timing, subject visibility and audio. Save/Share
   is still a separate, user-initiated action.

## Safety and compatibility

- **Never** auto-approves ASR text, unreviewed speech boundaries or
  low-confidence words. No render request before explicit confirmation.
- The existing service performs owner/accepted-source identity, review
  revision, 60-second, queue, disk, byte-limit and output verification.
- A saved local preset is account scoped. No transcript or video bytes are
  placed in it. The app never sends arbitrary FFmpeg filter syntax.
- Lack of portrait/manual-crop/soft-fades support downgrades to the existing
  closed compatible choices rather than sending an unsupported request.
- Caption layout HTTP 422 is disclosed and uses a plain video preview.
  Network and authentication failures abort; there is no silent fallback.
- Duplicate confirmation taps are ignored; retry recovery reuses the existing
  durable per-intent idempotency key. A token/account/project switch fences
  a delayed response from navigating the new session.
- There is no automatic publish, external AI service, new cloud worker,
  database migration, paid subscription or new video format.
- Candidate #1 is technically ranked by current confidence, coverage and
  duration heuristics. This is not semantic understanding, popularity
  prediction, subject detection, or a fully autonomous professional editor.

## Physical-device acceptance before rollout

1. Load a source where English analysis is complete but transcript review
   is not saved. **Prepare a Short draft** should only offer human review,
   never an automatic render.
2. Save the correct human review. Open the source and tap **Prepare a Short
   draft**, then cancel at confirmation. Verify no new preview job.
3. Confirm a draft using Fit + clean captions and compare the rendered video
   against the source and top candidate: 9:16, original voice, accurate
   caption text, boundaries and duration <=60s.
4. Save a custom appearance/voice/crop preset and prepare another draft.
   Confirm selected settings and quality against a real speech recording.
   Revert settings that raise background noise or hide faces.
5. Try a selected candidate whose caption layout exceeds limits. Confirm
   the plain-video fallback is explicitly disclosed *before* queuing.
6. Simulate intermittent connectivity, repeated tapping and a token refresh.
   Ensure no duplicate jobs, cross-account preview, or confusing stale screen.
7. Try the existing **Review English clips** and **Polish selected clip**
   manually; they must continue working unchanged.

## Deploy

Mobile-only change. After PR review and mobile CI, update the **Windows mobile
checkout**, retaining the correct `.env.local` private HTTPS API URL and
`EXPO_PUBLIC_ENGLISH_REVIEW=true`. Start Expo Go over USB using the proven
port 8082 reverse connection. Do **not** redeploy or modify the healthy VPS,
Caddy, offsite backup automation or database for this feature.
