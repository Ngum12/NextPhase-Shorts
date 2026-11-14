# Auto Editor V3 — reviewed English editorial-cue ranking (increment 1)

## Purpose and honesty
This is a **deterministic, explainable heuristic improvement** to the clip
selection stage, not an LLM, semantic story comprehension, emotional analysis,
viral prediction, auto-publication or a new rendering style. It is a first step
toward better selections. Words are untrusted data, not instructions.

The existing technical score still measures model word-confidence, speech
coverage and requested duration. New reviewed plan
`sentence-window-v5-discourse-reviewed` adds a small **ranking-only** adjustment
for easy-to-audit *English language cues*:

- Starts such as "but", "because", "therefore", "it" or "this" have a small
  penalty because they **may** rely on something earlier.
- Clear question-style beginnings ("why", "how", "what", etc.) and selected
  explicit introductions ("imagine", "today", etc.) get a small bonus.
- Some words near the ending ("solution", "learned", "worked", etc.) get a tiny
  potential-resolution bonus. Presence of a word is not proof of a conclusion.
- An initial "uh" or "um" gets a penalty.

Adjustments are bounded to -0.18 through +0.135; temporal-overlap diversity
still gives other source regions a chance. The preserved `Candidate.score`
field remains the **original technical score**, not a forged editorial score.
No source word interval, confidence, reviewed sentence end or media file is
modified. Unreviewed plans stay on v2; no render can occur before human review.
Non-English text is not scored with English lexical cues.

## Identity and backward compatibility

Existing v1/v2/v3/v4 plans, their JSON and immutable review revisions
remain readable without a migration or a background re-ranking task.
Only a **new explicit Save review** computes the new v5 order. For v4 and v5,
revision hashing includes the exact immutable ranked plan. New v5 options
cannot be accidentally rendered using an earlier numbered v4 clip choice:
stale revision numbers are rejected. Previously admitted preview idempotency
replays continue returning their existing jobs and original source ranges.

The mobile UI describes the new ranking as **technical + simple English
opening/ending cues, not verified story meaning**; legacy proposals continue
to show their older technical-only explanation. The original human-review
screen also explains the v5 limitations. It does not generate AI text,
automatically choose to publish or queue all three drafts.

## Privacy, resources and invariants

No external AI/model/API key, new database table, dependency, phone rendering,
cloud bill, or persistent transcript event is introduced. Only the existing
owner-authenticated and source-validated review text feeds the bounded ranker;
no script execution, model prompt, logging of personal transcript text, or
provider upload. Candidate count/time limits and the 60-second maximum still
apply; server-side FFmpeg and owner confirmation are unchanged. The
existing storage budget and cleanup controls remain intact.

## Validation

Regression tests cover revised ordering against the unmodified technical
ranker, first-word context/filler and ending cues, non-English neutrality,
repeatable ordering, legacy v4 read/revision compatibility, strict sentence
boundaries/duration, human review, privacy and unchanged render admission.
GitHub backend/mobile tests and Android bundling must pass before release.

After merging, **do not restart the VPS merely because this PR exists**.
On a planned maintenance window, review the separate private VPS updater,
confirm a verified offsite backup, idle queue and healthy analysis assets,
and use the project's operator-approved update procedure. This is a
backend + mobile change, unlike PR #62. Never use `docker compose down -v`,
delete DB/media, clear journal/backup state, weaken the IP allowlist, or bypass
worker sandbox/storage checks. A backup failure or invalid host check blocks
upgrade, not grounds to disable safeguards.

On a real owned recording, save a corrected review using the new planner,
compare v5 options versus the old technical order, play their cut boundaries,
confirm exactly one preview, check original voice and captions, and inspect
Save/Share. Old already-saved reviews do not silently replan on GET.
If clips sound awkward, the user must be able to pick another option;
true semantic selection needs later model/evaluation work.
