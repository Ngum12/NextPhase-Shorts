# Speech-aware Short choices: evidence preview (mobile-only)

## Why
Previously the three technically ranked choices showed only duration and source
timestamps. Owners had to spend a storage-reserving render to understand what
a choice might say. This increments the already-reviewed choices UI only.

## How it works
After the owner has compared the transcript against the original and saved the
review, **Prepare a Short draft** uses the existing owner-authenticated,
source-validated analysis response to show up to three choices, each with:

- The first up to eight transcribed words and, for longer selections, the last
  up to eight words (display capped at 96 Unicode codepoints per excerpt).
- A context warning when the first word resembles a dependent continuation
  such as `but`, `however`, `so` or `because`. This is a cautious
  lexical heuristic, not a guarantee about the real story.
- Optional technical cues when existing verified PCM-energy measurements
  indicate low-volume audio near a proposed cut, or the bounded RGB sampling
  reports a possible visual change near the cut. A partially sampled ending is
  explicitly disclosed; unavailable visual data never implies no changes.

The existing reviewed candidate ranking and cut timestamps **do not change**.
No source bytes are sent to any new service; text stays in the owner's app and
is never written into preview intent keys or event logging. The review
revision and project/owner checks remain in place. No additional AI model,
network request, native dependency or server render is needed for these hints.

## Safeguards
- Unreviewed transcripts still require human checking before suggestions can
  render. Snippets are read-only and do not modify recognized text, sentence
  ends or caption edits.
- If words/candidate indexes are missing, the UI shows no fabricated excerpt.
- Evidence is non-semantic, approximate and bounded. It is **not** face,
  emotion, popularity, or topic recognition. Always listen before publishing.
- Listing or hiding choices does not enqueue jobs; **Render draft** queues only
  one explicitly confirmed choice using the existing private, idempotent API.
- If server storage is full, continue to use normal owner-controlled deletion
  and verified cleanup, not database hacks or weakened admission guards.

## Physical Android acceptance
1. Choose an original speech video with a saved and corrected English review
   that contains two or three candidates. Tap **Prepare a Short draft**.
2. Verify the spoken opening/end of each candidate matches the saved
   transcript, that long excerpts are abbreviated, and that any pause/scene
   cues are presented as uncertain guidance.
3. Verify **no new job** appears before **Render draft** is confirmed.
4. Try an option whose opening starts with "but" or "because": the context
   caution should appear; a clearly self-contained beginning should not
   receive this particular caution.
5. Confirm one option, check cut endpoints/caption timing/voice in the rendered
   private preview, then Save manually. Do not auto-publish.
6. Repeat with visual guidance unavailable, incomplete or with no nearby
   events; the UI must not claim a clean edit or guaranteed absence of change.
7. Exercise sign-out, offline/retry, review-revision conflict, duplicate taps,
   and deletion of an unwanted preview without affecting its original source.

## Rollout
After all GitHub mobile checks and PR review, merge to main and pull on the
Windows mobile checkout. Restart Expo Go with `--clear` and your existing ADB
USB reverse `tcp:8082` connection. Keep the existing private HTTPS API config.
**Do not deploy the VPS** for this feature. It has no backend/schema/worker
changes. Continue to develop semantic highlight scoring and real editing-style
engines in separate tested increments rather than claiming them here.
