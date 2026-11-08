# REST API — Stage 1 truth

Package 3 preserves public request/status shapes. Transient storage/internal
failures may return to queued with bounded backoff within the existing two
attempts; permanent/exhausted failures stay failed. Queue signals/dead letters
are private operator metadata. Claim renewal never extends the absolute attempt
budget. See QUEUE_RELIABILITY.md.

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
| GET | `/api/v1/me/storage` | Bearer | Owner-only storage limit, known reservations, inventory status and availability |
| GET | `/api/v1/me` | Bearer | Current user |
| GET | `/api/v1/jobs` | Bearer | Current user's 100 recent jobs |
| POST | `/api/v1/jobs` | Bearer | multipart video/settings plus rights_confirmed=true, consent_version=upload-rights-v1 |
| GET | `/api/v1/jobs/{id}` | Bearer | Owner-scoped job, status |
| DELETE | `/api/v1/jobs/{id}` | Bearer | Owner-only irreversible deletion; 202 schedules cleanup |
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

Deleted projects are hidden from lists/detail/download/cancel (404). Repeated
owner deletion returns 202; related session/key replay returns 410. See
[cleanup timing, tombstones and retained records](PROJECT_DELETION.md).

New upload admission reserves source plus bounded two-attempt rendering space;
409 indicates full/unverified account storage. Accepted sessions/replays remain
repeat-safe at capacity; deletion frees the reservation after media cleanup.
See [budget and inventory contract](SAVE_AND_STORAGE.md).

New uploads require the versioned affirmative rights/server-processing statement.
Session JSON uses a strict boolean; multipart uses the literal string true. Old
active sessions must be reconfirmed through key-preserving creation replay before
parts/completion. Owner-only POST /api/v1/upload-sessions/discard-by-key takes
only the Idempotency-Key header and fences late creation with an aborted tombstone;
no rights assertion is needed for discard. GET /by-key/{client_key} recovers metadata.
See [acknowledgement, media profile and upgrade contract](UPLOAD_CONSENT_AND_MEDIA.md).

Optional S3 jobs keep the same authenticated streaming download route. Owner-only
POST `/api/v1/jobs/{id}/download-link` issues an exact-key GET capability for 5–60 s;
local/not-ready jobs return 409, other-owner/deleted jobs 404. Already-issued URLs
remain usable until expiry or physical removal, including after logout/deletion.
See [object access and deletion boundaries](PRIVATE_OBJECT_STORAGE.md).

Optional strict `direct_upload: true` requests direct transfer for new upload
sessions when enabled; existing replay keys keep their mode/digest. `part-url`
signs only the next bounded incoming chunk; `part-commit/{grant_id}` verifies and
seals before advancing the DB offset. Old API parts remain supported for API
sessions. See [direct protocol, errors and cleanup deadlines](DIRECT_UPLOADS.md).

## Account deletion

Authenticated POST `/api/v1/account/delete` requires `current_password` and UUIDv4
`receipt_key`; 202 confirms account disabled with media cleanup scheduled. All
sessions/claims are revoked. POST `/api/v1/account/deletion-receipt` accepts only
the opaque key without bearer authentication for seven days; 200 returns coarse
status, unknown/expired returns 404. Both are rate limited. See ACCOUNT_DELETION.md.

## Operational readiness

GET `/health` remains process liveness. GET `/ready` returns 200 or 503 with only
`ok` and `service`, no-store, based on DB/current-schema availability. It does not
guarantee workers or object-provider readiness. Detailed snapshots are operator-only
CLI commands, with no public metrics endpoint. See OPERATIONS.md.

## Email actions and delivery capability

Migration 0014 adds optional `email_verified_at` / `email_verification_method` to /me.
Local_file proof stays development-only. Migration 0016 adds optional Resend delivery
via encrypted durable outbox. Read-only GET `/api/v1/auth/recovery-capabilities`
reports `delivery: disabled | local_file | email` and boolean `verification_enforced`.
POST password-reset/request takes email; email-verification/request requires bearer.
Both use generic 202 acceptance, never codes. POST password-reset/confirm takes
code/new_password; email-verification/confirm takes code. Confirmations require an
expiring one-use proof and return 204, never a session. Default disabled mode rejects
confirmation with 503. Auth input errors are sanitized 422/no-store. See AUTH_RECOVERY.md.

Real-channel confirmation requires an accepted outbox and sets method `resend`.
Different delivery methods cannot redeem one another's proofs. Generic request
acceptance means queued/eligible, not sent, delivered or account existence proof.
With verified policy enabled, upload creation, parts, direct grants/commits and
completion return 403 until `email_verified_at` is set by the real channel.
Sign-in/refresh/recovery, reads, abort/discard and deletion remain available.
Default sending/policy remain disabled. See EMAIL_DELIVERY.md for retry/caps/expiry,
in-flight cancellation and actual provider/inbox acceptance gates.
