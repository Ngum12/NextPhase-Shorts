# Choose up to three reviewed Short drafts — mobile-only increment

## Goal
On an **already analyzed and human-reviewed** English recording, the source
project's **Prepare a Short draft** action offers up to three **different,
already ranked** candidate regions rather than always selecting candidate #1.
The server's existing sentence-window-v4-diverse-reviewed plan chooses source
ranges with bounded technical scoring and temporal-overlap diversity; this
does **not** understand narrative meaning or predict popularity.

## Owner flow
1. Upload an owned English recording and wait for analysis. Check original
   recording and save correct transcript words and sentence boundaries.
2. Open the original project and tap **Prepare a Short draft**.
3. When two or three valid reviewed candidates exist, see **Choose one Short
   draft** with length and source start/end times. No preview job is created
   while browsing choices. A recording with one choice still opens its normal
   confirmation without an extra menu.
4. Tap exactly one option. The client fetches the currently saved review and
   verifies its revision matches the earlier list (stale choices must abort).
   Only the selected candidate gets appearance-preset/caption preflight.
5. Review the specific candidate's framing, captions, voice and disclosed
   limitations. **Not now** leaves no new job. **Render draft** queues only
   that option through the existing revision-fenced, owner-scoped, private,
   idempotent preview API.
6. Inspect the preview's cuts, caption placement, original voice and intended
   meaning. Saving/sharing remains a separate user action.

## Storage and scope
- No automatic batch render. The **other** options cost **zero render jobs
  and zero new video storage** until the owner later requests one.
- Each requested preview does have its usual conservative storage reservation.
  If the server says the storage budget is full, use the normal project-delete
  workflow **only on an unneeded preview**, after exporting any wanted video.
  Do not bypass the storage guards or alter server accounting from the phone.
- Up to three candidates are displayed even if the reviewed server plan
  produces up to five. Existing selected-clip and polished edit workflows
  remain available for advanced manual control.
- No extra model, backend deployment, migration, subscription, cloud provider,
  API key, background phone processing or public sharing change.

## Acceptance on a real Android phone
- Already-reviewed source with 3 candidates: tap **Prepare a Short draft**,
  verify three options and **no new job** until selecting one and confirming;
  render option 2 and verify the actual source range matches option 2.
- Cancel confirmation: no job. Tap twice on render confirmation: one job.
- Modify the review after listing: old selection must be rejected, not render.
- A source with one reviewed candidate: original one-action prompt still works.
- A source without saved review: navigate to **Review English clips** without
  rendering. Recheck uncertain words against original audio.
- If captions don't fit, the chosen option falls back to a disclosed
  caption-free preview only for HTTP 422; other failures do not queue.
- Test low storage, network error, sign-out and project switches; confirm
  account/session fencing and previous manual preview routes.

## Release
After PR review and successful mobile CI, merge to main and pull latest on
**Windows**. Retain the working HTTPS API and
`EXPO_PUBLIC_ENGLISH_REVIEW=true`. Restart Metro in Expo Go with `--clear`
and existing USB ADB reverse port 8082. **Do not redeploy Contabo**: the
current server already exposes the reviewed proposal and selected-preview API.

This is step one toward automatic editing; story-aware highlight scoring,
genuine distinct editing styles and automatic multiple finished exports are
future milestones, not implemented by this PR.
