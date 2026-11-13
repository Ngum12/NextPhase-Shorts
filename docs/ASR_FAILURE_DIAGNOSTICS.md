# Diagnosing a failed Whisper transcription safely

## Observed 2026-11-13 private pilot failure

The owner uploaded an English recording lasting 29.905 seconds. The job
terminated after 235.5 seconds, with `transcribe` returning an error after
217.4 seconds. Visual sampling, source copy, audio extraction and audio energy
analysis succeeded. The worker's current cgroup memory.events showed
`oom 0` and `oom_kill 0`, and the trusted artifact/sandbox readiness check
returned `ready=true`, `enabled=true`, `inference_tested=false`.

These measurements do **not** prove what happened inside Whisper: a nonzero
subprocess exit and a rejected model output were previously both surfaced as
`ANALYSIS_FAILED`. The existing stderr/stdout suppression was intentional.

## Change

Only a finite code from the protected worker's following outcomes can reach
`RenderJob.error_code` and the owner-only analysis status endpoint:

| Code | Meaning | Next operator investigation |
| --- | --- | --- |
| `ASR_PROCESS_FAILED` | Whisper/native wrapper returned nonzero | Inspect CPU/runtime restrictions and verified engine compatibility; no raw stderr |
| `ASR_DEADLINE_EXCEEDED` | Protected native job crossed its configured timeout | Review host load and worker time budget, not unlimited retry |
| `ASR_OUTPUT_INVALID` | Missing, oversized or non-JSON result | Check bounded output generation and storage constraints |
| `ASR_WORD_TIMING_REJECTED` | Token time bounds/order exceeded strict repair limits | Investigate ASR token timestamp algorithm on synthetic fixtures |
| `ASR_TRANSCRIPT_REJECTED` | Transcript's language, token structure, fields or validation failed | Investigate parser compatibility using synthetic fixtures only |

Unclassified `MediaError` remains `ANALYSIS_FAILED`. No exception string,
recording, ASR text, engine path, command, stderr, stdout, PID, signal number or
return code is stored in the new category. Cancellation and existing retry
fences are unchanged. A failed task is not retried automatically.

The mobile project screen translates only these codes into fixed human-readable
messages. Unknown codes are shown as "precise cause not available" and never
interpolated into user-visible text.

**Existing failures retain `ANALYSIS_FAILED`**; the new diagnostic works
only on attempts run **after** the updated backend is deployed. A future failed
attempt will show its category in the mobile UI, as well as the owner-scoped
API response.

## Release and acceptance

1. Require backend tests and mobile checks, then review/merge the PR.
2. On the VPS, pull the merged `main`. Use the normal backup-first private
   update command `.venv/bin/python scripts/update_private_vps.py --apply`;
   it refuses to update without a fresh authenticated offsite-verified backup.
   Do not change models, memory limits, service exposure or secrets.
3. On Windows, pull merged `main`, keep `EXPO_PUBLIC_ENGLISH_REVIEW=true`
   and the existing private HTTPS API, and restart Expo Go using the proven USB
   `adb reverse tcp:8082 tcp:8082` flow with a cleared Metro cache.
4. On the same original project's English clip section, use **Retry English
   analysis** once. Keep original media intact and do not re-upload. If it
   fails again, record the **fixed code** displayed in the app or read it
   through the restricted DB. Verify privacy, timing, and voice still pass
   manual checks when transcription succeeds.

This is a diagnostic hardening change, not a guarantee that Whisper transcription
will succeed on every recording. Follow the newly observed fixed category with
a separate targeted root-cause fix. Tests use synthetic media/protocol fixtures;
real speech quality and runtime acceptance require a private device run.
