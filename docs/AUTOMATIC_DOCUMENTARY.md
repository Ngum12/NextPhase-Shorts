# Automatic documentary app pilot

This connects the scene engine to an authenticated project action. On an analyzed
English recording, **Create documentary (experimental)** queues a finished private
video without sentence marking, manual image selection or storyboard approval.
This first app version uses researched photographs and original footage/voice;
it does not promise a finished production Documentary style.

## What the creator does

1. Upload an original English recording (up to three minutes) using the existing
   upload flow with server English analysis enabled. Wait for speech analysis.
2. On the original project, tap **Create documentary (experimental)**.
3. Read and accept the Google transcript-sharing and Wikimedia research prompt.
   Only non-sensitive recordings that the creator has permission to share should
   be used. Google receives the chosen spoken excerpt; Wikipedia/Commons receive
   a public-topic query derived from it. No original video/audio is uploaded to
   those services. Google free-tier data-use terms still apply.
4. The app opens the queued documentary project. Leave it open or return later.
   The worker plans, researches, chooses relevant photographs, renders, and checks
   the output. Progress is described honestly without invented percentages.
5. Play the result; check that the imagery matches the story. **View visual
   sources** shows the creator, public source page and declared license. Save or
   share using the existing controls. Nothing publishes automatically.

Original footage appears at the beginning and end, with one or two researched
photographs in the middle and restrained image motion. Headings quote bounded
consecutive words from the recording; the model cannot fabricate headline claims.
The selected source interval and original audio stay continuous throughout. Final
output is 1080×1920 at 30fps, 5–60 seconds, within the creator's requested cap.

The initial excerpt is the best standard automatic suggestion. Gemini directs
research and selects relevant offered images; this action does not claim to
perform a new full-transcript passage search. Existing Gemini passage creation
remains separately available. Wikipedia retrieval and asset-title relevance
screening do not verify spoken claims or establish universal copyright clearance.

## Server prerequisites and updating

The existing private English analysis and Gemini pilot configuration is reused:
English review/analysis enabled, authenticated owner allowlisted, server-only
Gemini key present, and a confirmed billing-disabled free-tier Google project.
No key belongs in the mobile app and no additional subscription is introduced.
Public HTTPS access to `en.wikipedia.org`, `commons.wikimedia.org` and
`upload.wikimedia.org` is required from the server orchestrator. Native media
children keep their existing network denial, filesystem and resource controls.

After this change is merged, use the existing owner-controlled updater while the
app is closed and jobs have finished:

```bash
cd ~/NextPhase-Shorts
git switch main
git pull --ff-only origin main
sudo -v
.venv/bin/python scripts/update_private_vps.py --apply
```

Continue only after `"ok": true`. Update the Windows checkout and restart Expo
with the existing API URL; no new mobile environment variables are required.
The globally advertised style catalog remains unchanged: this is an allowlisted
pilot action on a prepared project, not six completed style engines.

## Admission, costs and retries

- `POST /api/v1/jobs/{source}/analysis/documentary` requires both explicit consent
  acknowledgements and `documentary-research-v1`. It accepts no source paths,
  asset URLs, model code, client storyboards or replacement transcript.
- One source project has one durable documentary job. Concurrent requests, lost
  replies and app restarts reopen the same job; they cannot spend again. A deleted
  documentary returns 410. A failed documentary stays failed when reopened.
- Admission holds the owner lock, verifies the accepted source/checksum, reserves
  queue/storage capacity, checks operator budget controls, and atomically reserves
  **two** calls in the existing shared Gemini daily allowance (5 per owner,
  20 globally, or lower configured values). Failures consume committed allowances.
  Uncommitted admission failures roll back both the job and the reservation.
- Before each provider call, a claim marker is durably fenced by owner, job token,
  lease and hard deadline. Completed direction, numeric token usage and timings
  are persisted. A crash with an in-flight marker fails closed on recovery rather
  than automatically repeating the call. Raw provider output is never stored.
- Research allows at most three requests/three downloads/24MiB per session; this
  flow uses two searches and at most two JPEG downloads. Redirects, arbitrary
  origins, unsupported encodings and unsupported license metadata are rejected.
  Actual source size/dimensions are filtered before downloading. A second Gemini
  call may decline all images instead of choosing irrelevant filler.
- The entire documentary pipeline shares a maximum **300-second** budget, lowered
  by the configured render timeout. Planning/research consume that budget; the
  compositor receives only the remaining time. No existing worker lease, render
  deadline, native-stage limit, output cap or sandbox setting is increased.
- Each of two possible attempt directories is conservatively reserved for two
  source copies, downloaded assets plus verified copies (48MiB), voice (16MiB),
  scene files (64MiB), bounded metadata (1MiB) and the configured output cap
  (maximum 64MiB). Attempt-local inputs/assets/scenes are cleaned on normal exits;
  the existing retention/deletion system handles interrupted attempt trees.
- A successful attempt retains only its output and a bounded private source/scene
  manifest. Authenticated owner-only source access uses no-store caching. Parent
  deletion revokes all descendants and erases their specifications; account
  deletion, retention and restore-journal fencing continue to apply.

Fixed `DOCUMENTARY_*` codes distinguish research, rights, planning, download,
source and rendering failures. Deadline/output-limit codes remain the existing
ones. No transcript, raw ASR/provider output, credentials or native stderr enter
logs. Research is source material, not a truth check; `claims_verified` is false.

## Acceptance and limits

Tests exercise consent, ownership, free-tier availability, shared budget denial,
capacity rollback, idempotence, provider output validation, claim interruption,
expiry/takeover/deletion fencing, and terminal research failure. An integration
test uploads real synthetic media, submits the authenticated documentary request,
runs the leased worker through real FFmpeg rendering, downloads the result and
reads attribution, then verifies parent deletion revokes both. Network providers
in that integration test are mocked; it is not a live Gemini acceptance test.

The separate engine demonstration has exercised live public Wikimedia research
and a rendered Apollo example. This host does not support strict Landlock, so a
protected VPS/phone acceptance run remains required after owner deployment. Do
not claim it has been performed here. Stock-video search/selection, rich caption
composition, music, speaker-aware reframing, claim verification, qualitative
benchmarks and a more flexible creative storyboard remain further work.
