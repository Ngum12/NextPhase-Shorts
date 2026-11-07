# Direct resumable chunks: opt-in development increment

Default: `DIRECT_UPLOADS_ENABLED=false`. Existing PC/Pixel uploads remain API-mediated.
Enable only with the already-reviewed private, nonversioned S3 backend. No cloud
resources, credentials, policies or billing are provisioned by this feature.
All encoding, validation and rendering remain on servers; output stays 9:16, <=60 s.

## Protocol and immutable acceptance

1. Updated clients send strict boolean `direct_upload: true` with the usual
   rights-confirmed session descriptor. If enabled on the server, a **new** session
   returns `transfer_backend: "direct-s3"`. Otherwise it returns `api`. Existing
   sessions keep their mode, key, offset and rights record across upgrades/replays.
   This capability field is excluded from the old immutable descriptor digest.
2. Owner-only POST `/api/v1/upload-sessions/{id}/part-url` accepts `{offset,sha256}`.
   The offset must be the next server-acknowledged boundary. The expected length
   comes from negotiated chunk size/remaining bytes, never a client size/path.
   Exactly one durable grant/key per session/offset prevents renewed links from
   accumulating additional remote objects. Changed checksums under that offset
   are refused. An already committed matching offset returns its session state.
3. The reply contains `grant_id`, a SigV4 PUT URL, required headers and expiry.
   Signed length, content type, SHA-256 checksum and metadata bind the capability
   to one random **incoming** key. Lifetime defaults to 60 s, configurable 5–60 s
   (shorter near session expiry). URLs/responses are private/no-store and never
   stored in the journal or general logs. No link is issued for expired, discarded,
   deleted, wrong-owner or unacknowledged footage.
4. The phone PUTs only that bounded chunk to storage, without its API bearer,
   cookies or redirects. The current client accepts HTTPS or development loopback
   HTTP origins, sends only the required storage headers, and retains its private
   copy/journal on network or expired-link failure. Resume requests a new link
   for the same unacknowledged key. A lost PUT reply may require retransmission;
   an acknowledged chunk is skipped after runtime restart.
5. Owner-only POST `/{id}/part-commit/{grant_id}` downloads the incoming object on
   the server, checks exact length and full SHA-256, then writes a separate server-
   owned **sealed** key. Only that sealed reference enters the authoritative part
   manifest. No URL ever authorizes writes to a sealed key, original or result.
   Concurrent/repeated commits advance the offset once. A lost commit response is
   recovered from GET session state. Abort/expiry/deletion during object I/O prevents
   publication when the owner lock/state is checked again.
6. Completion streams sealed chunks into private server assembly, rechecks every
   digest/length and the whole source, probes media/rights/limits, and creates one
   queued S3 job. Existing claim fences, output QA, <=60 s cap and download routes
   apply. Upload I/O is not video encoding on the phone. API disk is still required
   for validation/assembly; these workers/services are not fully stateless.

Object keys are server UUIDs under `uploads/{owner}/{session}/incoming/{grant}`
and `.../sealed/{grant}`. No title, filename, client path, public URL or client ETag
selects storage targets. A mutable incoming object is **never** an accepted source.
Even if a storage service accepts a bad checksum payload, API full-byte verification
refuses it. Replaying a still-live incoming link after acknowledgement cannot
change the sealed bytes used for completion. S3 reference/namespace checks retain
all safeguards described in PRIVATE_OBJECT_STORAGE.md.

## Access, budgets and cleanup

Links are short-lived bearer capabilities, not login sessions. Logout/Abort cannot
recall an already-issued PUT. It can write only its bounded incoming key until
expiry (provider may allow a write begun before expiry to finish later); API
mint/commit/complete still enforce current authentication and terminal state.
Never log, publish or send links to analytics. TLS, bucket public-access denial,
ACL restrictions, ingress/request/egress limits and provider policy review remain
production gates. Native mobile does not require browser CORS; web CORS/provider
compatibility is not automatically configured or claimed.

Admission reserves **three declared source copies plus two render caps** for a
direct session, allowing incoming + sealed + assembled/retained source. This
conservative reservation transfers to the job without double charging and stays
until project deletion cleanup; it is not refunded as temporary copies disappear.
Account shows used/reserved budget, not actual provider usage or paid credits.
API sessions keep their previous one-source reservation. Offline inventory
reconstructs this declared direct-session budget instead of guessing it as one.
These are admission budgets, not strict physical storage or monetary quotas.
Local assembly, source publication and worker scratch can transiently duplicate
bytes beyond these retained-copy reservations.

Abort/expiry/completion cleanup waits until all recorded PUT capabilities expire.
It removes the canonical incoming/sealed prefix and private staging. Aborted or
expired sessions stay charged until successful cleanup; project deletion releases
its job reservation only after both project objects and session staging are gone.
Deleted projects stop new API access immediately; 202 still means scheduled removal.
Terminal direct sessions and deleted projects are rescanned in bounded batches for
late/in-flight writes. Failed removal/namespace changes retain or restore pending
cleanup state. Grant/operational tombstones remain; no full personal-data erasure
or legal retention guarantee is claimed. Long-lived in-flight writes, abandoned
unaccepted originals, versioned backups and global cleanup/load limits remain open.

## Migration and setup

Migration **0011_direct_uploads** adds session transfer/namespace/cleanup fields,
optional remote-part references and a one-grant-per-offset table. Existing sessions
remain `api`; existing parts, offsets, jobs, accounts and receipts are preserved.
No re-login or mobile native dependency is introduced. Update API/mobile together
before opting into direct sessions; old clients cannot send API chunks to a session
already established as direct. Turning the feature off stops new direct admissions;
existing direct sessions still need their S3 namespace/credentials for continuation.

Server-only settings:

```dotenv
MEDIA_BACKEND=s3
DIRECT_UPLOADS_ENABLED=true
SIGNED_UPLOAD_SECONDS=60
# Existing S3 endpoint/bucket/scoped credentials remain required.
# S3_PUBLIC_ENDPOINT must be client-reachable; never use Docker-only names on a phone.
```

Keep the owner's normal PC on local storage and the flag off until a separate
S3 setup is reviewed. After stopping API/worker/Expo and backing up DB/media:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull
$env:PYTHONPATH = 'apps/api'
$env:MEDIA_BACKEND = 'local'
$env:DIRECT_UPLOADS_ENABLED = 'false'
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm run typecheck
npm run test:uploads
npm run test:auth
npm run test:exports
```

No new dependency installation/npm native rebuild is needed solely for this change.
Backend tests force local/off defaults regardless of a developer's normal storage
configuration; the unit store is mocked and the explicit S3 smoke is loopback-only.

From repo root with Docker, run `.venv/bin/python scripts/smoke_object_store.py`
(Windows: `.\.venv\Scripts\python.exe scripts/smoke_object_store.py`). It enables
short-lived direct URLs only in its disposable generated-credential environment.
Real tests interrupt a PUT halfway, restart the API, resume a 51 MiB source at the
1 MiB acknowledged offset, reject expired links, renew the same key, reject changes
to the signed sealed path/length, complete as one job, render/decode 1080×1920 MP4,
and verify physical project plus upload-prefix removal. The expiry waits are
correctness checks, not performance measurements or production SLAs.

## Acceptance still required

Client tests use native/network adapters. Pixel default API regression, plus a
separately configured local-S3 direct upload/pause/restart/expired-link/discard test,
remain owner acceptance steps. USB testing needs `adb reverse` for the configured
S3 public port as well as API/Metro. No actual direct Pixel or iOS test, OS background
transfer, browser CORS test, general-provider certification, production isolation,
load/soak, paid deployment or full privacy/license clearance is claimed.
