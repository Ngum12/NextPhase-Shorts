# Optional Gemini clip selection — private development pilot

After English analysis, **Create with Gemini** lets Google choose a coherent
excerpt from the existing source-validated shortlist (at most five ranges).
This adds a content-aware selection step; it does not yet compose multiple scenes,
rewrite speech, create new timings, generate B-roll or certify story quality.
**Create suggested Short** still uses the existing local heuristic selector.

The owner must accept the transcript-sharing prompt for each action. The server
sends the complete recognized transcript and proposed excerpt text to Google,
with their candidate IDs and durations. No audio/video, account IDs, project IDs,
filenames or signed media URLs are sent. Google's free-tier terms may permit using
submitted text to improve its products; use non-sensitive development recordings
and only material you are authorized to share. ASR estimates can contain errors.
Do not treat the model's choice as verified meaning or accurate captions.

## Activate on the existing VPS

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

When Gemini succeeds, the confirmation says **Gemini selected this excerpt**.
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
- Provider output is a strict one-field JSON integer ID of an offered candidate,
  or zero to decline. Duplicate keys, unknown IDs, tool calls, generated ranges,
  explanations and extra fields are rejected. Opaque provider signatures are
  ignored and discarded. Transcript instructions remain quoted untrusted data.
- Stored metadata contains only plan hash, request UUID, consent version/time,
  model, chosen ID/status, fixed failure code and bounded token/time usage when
  available. No raw provider output, signatures or transcript copies. HTTP errors
  are replaced with fixed codes, never logged with their response bodies.
- Failure codes: `INPUT_INVALID`, `NOT_CONFIGURED`, `MODEL_UNSUPPORTED`,
  `PROMPT_TOO_LARGE`, `PROVIDER_AUTH_FAILED`, `PROVIDER_RATE_LIMITED`,
  `PROVIDER_UNAVAILABLE`, `OUTPUT_INVALID`, `MODEL_DECLINED`, `DAILY_LIMIT`,
  `PENDING_EXPIRED`. They never contain recognized speech or raw provider text.
- Selected and fallback plans bind source/transcript, candidate order and current
  revision. Preview intents additionally distinguish Gemini from standard mode;
  immutable excerpt specs retain model/status provenance. Rendering accepts only
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
