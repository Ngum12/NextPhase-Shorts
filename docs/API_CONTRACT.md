# REST API — Stage 1 truth

Base URL: `http://localhost:8000` in development only. Production must be HTTPS, authenticated and routed behind edge protections.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | No | Basic health |
| GET | `/api/v1/styles` | No | Planned presets; `available=false` is truthful |
| POST | `/api/v1/auth/register` | No | `{email,password}` -> JWT, 12–128-char new password |
| POST | `/api/v1/auth/login` | No | `{email,password}` -> JWT |
| POST | `/api/v1/auth/logout` | Bearer | Revoke this session, 204 |
| POST | `/api/v1/auth/logout-all` | Bearer | Revoke all account sessions, 204 |
| POST | `/api/v1/auth/password` | Bearer | Verify current/change password, revoke all sessions, 204 |
| GET | `/api/v1/me` | Bearer | Current user |
| GET | `/api/v1/jobs` | Bearer | Current user's 100 recent jobs |
| POST | `/api/v1/jobs` | Bearer | multipart `file`, `title`, `style`, `desired_seconds` |
| GET | `/api/v1/jobs/{id}` | Bearer | Owner-scoped job, status |
| POST | `/api/v1/jobs/{id}/cancel` | Bearer | Owner-only queued/processing cancellation; repeat-safe |
| GET | `/api/v1/jobs/{id}/download` | Bearer | Owner-scoped MP4 when succeeded |

Upload accepted extensions `.mp4`, `.mov`, `.m4v`, `.webm` with content verified by FFprobe. Source duration <=600 s, <=314572800 bytes. Requested `desired_seconds` between 5–60. Worker currently trims beginning of input and pads image into portrait 1080x1920 at 30fps; **no style-dependent effects**.

Job statuses: `queued`, `processing`, `succeeded`, `failed`, `cancelled`. Basic error codes: `RENDER_FAILED`, `INTERNAL_ERROR`, `MAX_RETRIES`.

**Future changes (must be versioned):** cloud signed upload URLs, immutable render version IDs, stage/progress APIs, EDL endpoint, storyboard approval, revisions, billing events, entitlements, admin, audit, deletion and notifications.

Queue controls: optional owner-scoped `Idempotency-Key` on uploads, fingerprinted
against content/settings. Replay returns 200 with Idempotency-Replayed=true;
key conflict 409; full active queue 429 with Retry-After. Cancellation returns 200
(repeated cancellation stays cancelled), terminal succeeded/failed returns 409.
Default max active=3 and max processing=1 per user. See [queue controls](QUEUE_CONTROLS.md)
for exact semantics, races and remaining resource limits.

Durable sequential upload sessions are now available at `/api/v1/upload-sessions`
(create/get/PUT parts/complete/abort), reserving the same active-job capacity as
legacy uploads. See [resumable uploads](RESUMABLE_UPLOADS.md) for checksums, status,
fixed-size part rules, expiry and restart behavior. Legacy multipart remains
supported; the mobile Create Short flow now uses upload sessions.

Auth tokens now require a persistent session record (migration 0005). Existing
users sign in once after upgrading. Responses include expires_in; default TTL
24 hours. Login/register/password changes have shared fixed-window limits and
429 Retry-After. See [session semantics and upgrade guide](AUTH_SESSIONS.md).
