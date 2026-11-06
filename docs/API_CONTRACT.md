# REST API — Stage 1 truth

Base URL: `http://localhost:8000` in development only. Production must be HTTPS, authenticated and routed behind edge protections.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | No | Basic health |
| GET | `/api/v1/styles` | No | Planned presets; `available=false` is truthful |
| POST | `/api/v1/auth/register` | No | `{email,password}` -> JWT, min 10-char password |
| POST | `/api/v1/auth/login` | No | `{email,password}` -> JWT |
| GET | `/api/v1/me` | Bearer | Current user |
| GET | `/api/v1/jobs` | Bearer | Current user's 100 recent jobs |
| POST | `/api/v1/jobs` | Bearer | multipart `file`, `title`, `style`, `desired_seconds` |
| GET | `/api/v1/jobs/{id}` | Bearer | Owner-scoped job, status |
| POST | `/api/v1/jobs/{id}/cancel` | Bearer | Owner-only queued/processing cancellation; repeat-safe |
| GET | `/api/v1/jobs/{id}/download` | Bearer | Owner-scoped MP4 when succeeded |

Upload accepted extensions `.mp4`, `.mov`, `.m4v`, `.webm` with content verified by FFprobe. Source duration <=600 s, <=314572800 bytes. Requested `desired_seconds` between 5–60. Worker currently trims beginning of input and pads image into portrait 1080x1920 at 30fps; **no style-dependent effects**.

Job statuses: `queued`, `processing`, `succeeded`, `failed`, `cancelled`. Basic error codes: `RENDER_FAILED`, `INTERNAL_ERROR`, `MAX_RETRIES`.

**Future changes (must be versioned):** upload sessions with resumable signed URLs, immutable render version IDs, stage/progress APIs, EDL endpoint, storyboard approval, revisions, billing events, entitlements, admin, audit, deletion and notifications.

Queue controls: optional owner-scoped `Idempotency-Key` on uploads, fingerprinted
against content/settings. Replay returns 200 with Idempotency-Replayed=true;
key conflict 409; full active queue 429 with Retry-After. Cancellation returns 200
(repeated cancellation stays cancelled), terminal succeeded/failed returns 409.
Default max active=3 and max processing=1 per user. See [queue controls](QUEUE_CONTROLS.md)
for exact semantics, races and remaining resource limits.
