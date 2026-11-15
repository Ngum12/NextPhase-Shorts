# Optional Gemini clip selection — private development pilot

After English analysis, **Create with Gemini** can ask Google to find up to three
promising contiguous passages across the complete recognized transcript. This
removes the previous five-candidate shortlist restriction: a later passage can
be proposed even when the local heuristic did not offer it. The first model
proposal is prepared automatically; alternatives are optional. **Create suggested
Short** still uses the local heuristic selector.

The source is partitioned into bounded speech units that cover every recognized
word exactly once, in order. Google returns only unit IDs, never words or timing
edits. The server maps them to original word endpoints and rejects unknown,
backward, near-duplicate, too-short, over-duration, long-silence or broadly
unreliable ranges. This does not compose separate scenes, rewrite speech, generate
B-roll, interpret the video visually or certify semantic quality. Watch the result.

The owner must accept the transcript-sharing prompt for each action. The server
sends the complete recognized transcript as speech units with their validated
timing boundaries to Google. The older shortlist mode sends the full transcript
and candidate excerpts with IDs and durations. No audio/video, account IDs, project IDs,
filenames or signed media URLs are sent. Google's free-tier terms may permit using
submitted text to improve its products; use non-sensitive development recordings
and only material you are authorized to share. ASR estimates can contain errors.
Do not treat the model's choice as verified meaning or accurate captions.

## Activate on the existing VPS (first setup)

The key saved in the Codex cloud environment is **not installed on your VPS**.
The live API needs its own private server configuration. Do not put this key in
Expo variables, source files, a GitHub comment, shell command arguments or chat.

1. Review and merge the feature PR after its local validation evidence. GitHub
   Actions billing being blocked does not prevent running the local checks.
2. Close the phone app and allow active jobs to finish.
3. In the VPS SSH terminal:

   ```bash
   cd ~/NextPhase-Shorts
   git switch main
   git pull --ff-only origin main
   .venv/bin/python scripts/configure_gemini.py --enable
   ```

   First verify in Google AI Studio that this key's project has billing disabled,
   then type `FREE` at the helper prompt. Paste the key at the **hidden** prompt.
   The helper cannot inspect Google billing itself; request limits are not a
   substitute for keeping billing disabled. It preserves all other settings and
   atomically writes the existing private `.data/vps-trial/server.env` (0600).
   Symlinks, hardlinks, public files and invalid key formats are refused. It does
   not make an API call or restart anything.
4. Run the normal backup-first updater:

   ```bash
   sudo -v
   .venv/bin/python scripts/update_private_vps.py --apply
   ```

   Continue only after `"ok": true`. Migration `0026_gemini_selection` adds a
   nullable metadata column and preserves old transcripts, reviews and jobs.
5. In Windows PowerShell, update and restart Expo:

   ```powershell
   cd C:\Users\Ngum\NextPhase-Shorts
   git switch main
   git pull --ff-only origin main
   cd apps\mobile
   & "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" reverse tcp:8082 tcp:8082
   npx expo start --go --localhost --port 8082 --clear
   ```

   Keep your existing HTTPS API and English-pilot app settings.

## Update an already-working Gemini installation

Keep the existing key, free-tier gates and owner allowlist. After merging this
feature, close the app and finish active jobs, pull main on the VPS and run the
usual backup-first updater. Pull main on Windows and restart Expo with the existing
API/English-pilot settings. No new key, flag, migration, upload or ASR run is needed.

On an existing analyzed original, tap **Create with Gemini**, accept the updated
transcript/timing-sharing explanation and confirm **Render draft**. The first
explicit passage-mode request can replace a completed legacy shortlist cache
with one new budgeted call. Subsequent openings, caption checks and renders reuse
that result. The chosen start/end may differ from the previous clip and its length
can be shorter than the requested maximum to preserve a complete thought.

Older apps/servers retain the existing shortlist protocol. An in-flight old
request is never overwritten or automatically duplicated by a new mode request.
Both modes share the same daily request budgets. A completed passage cache is
also readable by an older app without another provider call.

## Test in the app

1. Open an original English project whose analysis is already ready, or upload a
   non-sensitive English recording and run **Find English clips**.
2. Tap **Create with Gemini**, read the sharing explanation, then **Agree and create**.
3. The app prepares Gemini's first choice automatically; no sentence marking or
   individual word confirmation is required. Tap **Render draft**.
4. Watch the resulting private Short. Check whether the opening makes sense,
   the ending completes the thought, qualifications remain intact, and captions
   match the recording. Save/share only after watching it.
5. To compare, return to the original and use **Create suggested Short**. These
   are separate render intents. Comparing choices creates no extra render jobs;
   only confirmed renders consume render/storage capacity.

When passage mode succeeds, the confirmation says **Gemini selected this passage
from across your transcript**. Older shortlist mode says **Gemini selected this excerpt**.
When it fails, declines or reaches a limit, the confirmation explains that the
standard selector is being used. Missing configuration hides the Gemini button;
old analyzed projects do not need another ASR run. A pending interrupted request
can be reopened; no automatic resend is performed.

A successful selection **or fallback is cached for the unchanged analysis**.
Reopening, caption preflight and rendering reuse it without another API call.
A failed choice is not automatically retried, even after the next day's reset;
use standard suggestions or a new project for a new evaluation. Updating a saved
transcript review changes the analysis revision and invalidates the cache.

## Limits, privacy and failure behavior

- Disabled by default. Both `GEMINI_PLANNING_ENABLED=true` and
  `GEMINI_FREE_TIER_CONFIRMED=true`, a server key, and the existing private English
  owner allowlist are required. Key files also work through `GEMINI_API_KEY_FILE`;
  configure either the environment key or its private file, never both.
- Fixed model `gemini-3.1-flash-lite`; one provider request per unchanged plan,
  no retries, redirects, automatic model upgrades or paid fallback. Limits are
  5 calls per owner per UTC day and 20 across the server per UTC day. Admission
  holds owner then global SQL locks, counts failed requests, and respects the
  existing budget emergency switch. No SQL locks are held while calling Google.
- At most 1,000 words, 24,000 UTF-8 source/options JSON bytes, 128 generated tokens and 65,536
  decoded response bytes. Connect timeout 5s, individual I/O timeout 10s, streaming
  elapsed check 30s (a final blocked read can add up to 10s). The 90s pending
  claim prevents duplicate calls if a process or client disappears.
- Passage output is strict JSON containing at most three offered speech-unit
  start/end ID pairs, or an empty array to decline. Older shortlist output remains
  a single integer candidate ID or zero to decline. Duplicate keys, unknown IDs,
  tool calls, generated timestamps,
  explanations and extra fields are rejected. Opaque provider signatures are
  ignored and discarded. Transcript instructions remain quoted untrusted data.
- Stored metadata contains only plan hash, request UUID, consent version/time,
  model, strategy, chosen ID or original word-index ranges/status, fixed failure
  code and bounded token/time usage when available. No raw provider output, signatures or transcript copies. HTTP errors
  are replaced with fixed codes, never logged with their response bodies.
- Failure codes: `INPUT_INVALID`, `NOT_CONFIGURED`, `MODEL_UNSUPPORTED`,
  `PROMPT_TOO_LARGE`, `PROVIDER_AUTH_FAILED`, `PROVIDER_RATE_LIMITED`,
  `PROVIDER_UNAVAILABLE`, `OUTPUT_INVALID`, `MODEL_DECLINED`, `DAILY_LIMIT`,
  `PENDING_EXPIRED`. They never contain recognized speech or raw provider text.
- Selected and fallback plans bind source/transcript, candidate order and current
  revision. Preview intents additionally distinguish Gemini from standard mode;
  immutable excerpt specs retain model/status/strategy provenance. Rendering accepts only
  existing original word endpoints, 5–60 seconds / 150–1,800 frames, inside both
  source and requested duration. Same checksum, caption/layout, sandbox, leases,
  cancellation, storage admission and deletion/publication fences still apply.
- Project/account deletion and restore replay remove this cache with the existing
  analysis row. A late provider result is discarded if the source is deleted or
  analysis changes. Deletion cannot recall text already sent to Google; provider
  retention/use is governed by its terms, separate from our own deletion.

## Reproduce local checks without GitHub Actions

```bash
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q
.venv/bin/python scripts/smoke_e2e.py
cd apps/mobile
npm run typecheck
npm test
EXPO_OFFLINE=1 npx expo export --platform android --output-dir /tmp/nextphase-gemini-android --max-workers 2
```

Backend tests isolate credentials and never contact Google. They cover strict
provider output, privacy-safe errors, explicit consent, private ownership,
transactional limits, cache reuse, pending expiry, stale/deleted sources,
caption/render intent separation, migration preservation, and a real synthetic
FFmpeg render/download. The live provider smoke used authored synthetic text
only; it is connectivity evidence, not a benchmark of editing quality.


## Gemini selected successfully, but the draft render failed

Selection and native video rendering are separate stages. A valid Gemini-selected
range can still hit the preview's 300-second render deadline. Updated workers
report `RENDER_DEADLINE_EXCEEDED` and preserve the original; older workers report
only `RENDER_FAILED`. Timeout classification does not raise any deadline or relax
resource/sandbox controls.

Preview rendering samples at 30fps and drops preroll before costly scaling and
caption drawing, preserving the original source clock and validated range.
After updating the VPS and mobile app, open the failed draft and tap **Back to
original project**, then **Create with Gemini** and **Render draft**. The cached
selection is reused without another provider call. The new explicit confirmation
replaces a terminal cached draft with one fresh render intent. A lost response
reuses that replacement key; repeated background renders are not introduced.

If the fresh job still reaches its deadline, retain it for privacy-safe stage
and source-profile investigation. Do not collect native stderr, transcript text,
caption contents, secret values or private media in general logs. Synthetic local
benchmarks do not establish speed on the owner's VPS or source recording.


### CPU-bound preview profile

Preview output uses the existing H.264/CRF 24 target with the `superfast` preset.
This reduces CPU work at the cost of larger files; the same 64 MiB file cap and
300s render deadline apply. No output resolution, duration, caption setting or
sandbox control is relaxed. Source seeking retains keyframe preroll and original
timestamps before the precise clip cut; leveling keeps full gain history.

The latest privacy-safe encode observations include numeric `frames` and
`frames_per_second`, alongside elapsed time, CPU and sampled RSS. Raw native
stdout/stderr, captions, transcripts and source paths are not logged. If a retry
still times out, these counters distinguish slow progress from failing before
frames are produced. Local synthetic benchmarks do not guarantee VPS throughput.


## Passage-mode contract and limitations

The complete source is represented by at most 128 ordered units, initially split
at punctuation, pauses, duration-aware boundaries and bounded word counts. Excess
adjacent short units are merged without dropping source words. Units are proposal
boundaries, not verified sentence endings. If the complete unit JSON exceeds the
existing 24,000-byte input bound, the request falls back; context is not silently
truncated. English/1,000-word bounds, 128 output tokens, 65,536 response bytes,
provider timeouts, request counts, free-tier/owner gates and no-retry policy remain.

A new `mode: passages` request requires `gemini-passages-v1` consent. Old requests
keep `gemini-transcript-v1` and shortlist mode. The nullable existing cache column
accepts a closed v2 proof containing original word-index ranges; old v1 records
and their render revision hashes remain compatible. Mode and mapped candidate
order bind the new revision, even when the chosen source range is unchanged.
No provider text, signatures or duplicate transcript is stored. Source/review
changes and deletion still fence late results, captions and new render admission.

One to three model proposals are ordered first; distinct local alternatives may
fill the remaining five slots. The phone identifies model alternatives separately
and preflights/renders only the chosen option. Semantic-quality verification stays
false: ASR estimates, speech-unit boundaries and the model's judgment can be wrong.
The native renderer, including its tested CPU profile and sandbox, is unchanged.

Development validation uses authored fixtures and mocked provider transport,
including a passage outside the old shortlist and a real rendered/downloaded
synthetic video. It proves the protocol and source constraints, not live semantic
quality. No live Gemini request or private-media evaluation was made for this
change. Phone/VPS acceptance should check whether the new chosen idea makes sense
and retains qualifications, answers and a complete ending before sharing.
