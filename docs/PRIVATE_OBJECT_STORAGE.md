# Private object storage: first working increment

The default remains `MEDIA_BACKEND=local`. Opt-in `s3` stores accepted originals
and rendered MP4s in an existing S3-compatible private bucket. It creates no cloud
account, bucket, billing resource or policy. Do not configure paid infrastructure
without the owner's approval. Local SeaweedFS is for isolated development tests.

## Data and access contract

- Migration **0010_object_backend** labels existing jobs `local`, preserving all
  original paths, accounts, acknowledgement records and pending upload offsets.
  New admissions record the selected backend and a private endpoint/bucket namespace
  fingerprint. Reads, rendering and deletion refuse a changed namespace; cleanup
  cannot mistake an empty replacement bucket for successful erasure. Changing the default does not move
  old media; both kinds remain readable. Keep the same S3 endpoint, bucket and
  scoped credentials available while any remote job remains. Bucket migration is
  not implemented; switching the bucket under existing references fails closed.
- Uploads still use the authenticated resumable API (or legacy multipart). The
  existing part journal, checksum verification, rights acknowledgement and storage
  reservations apply. Complete assembles/probes privately on the API host, then
  uploads the validated original before committing one job. Source bytes are not
  processed on the phone. API and upload staging still need a private shared volume.
- Keys use only canonical server UUIDs: `media/{owner}/{job}/input.{ext}` and
  `media/{owner}/{job}/{claim-token}/output.mp4`. Titles/client filenames never
  become object keys. Stored S3 references include SHA-256, not credentials or
  expiring URLs. No endpoint accepts a client bucket, object key or remote URL.
- Server uploads include SHA-256 metadata and a SHA-256 request checksum; verify
  stored length/metadata. Workers fetch into their attempt directory, bound the
  byte count and verify full source SHA-256 before passing a **local** filename
  to FFprobe/FFmpeg. Original local staging is removed only after confirmed DB
  commit; attempt input/output scratch is removed when the worker returns.
- Render success is committed only after validated output storage succeeds and
  the DB claim/lease fence still matches. Remote attempts have an additional
  transfer/probe lease margin (render timeout + 300 s). A lost claim cannot replace
  another attempt's artifact. Storage failures return 503 during admission or fail
  the render with `STORAGE_UNAVAILABLE`; they never report successful rendering.
  Source PUT/HEAD and output PUT/HEAD add network time; no speed claim is made.
- Existing `GET /api/v1/jobs/{id}/download` streams from the API with owner/session
  validation and private/no-store headers. It does not redirect. Mobile Save/Share
  keeps using this route, so bearer tokens stay on the API origin. No mobile source,
  native dependency or new app UI is needed for this increment.
- Owner-only `POST /api/v1/jobs/{id}/download-link` returns `{url,
  expires_in_seconds}` for a succeeded S3 job. Local jobs/not-ready jobs return
  409; missing/other-owner/deleted jobs 404; unauthenticated requests 401. The
  SigV4 URL is GET-only, for the exact output key, with attachment/no-store response
  parameters. Lifetime defaults to 60 s and is constrained to 5–60 s. Configure
  `S3_PUBLIC_ENDPOINT` to an explicitly reviewed client-reachable origin; it defaults
  to the internal endpoint only when the variable is absent. Do not send a bearer
  header when fetching this URL. This endpoint is available for integration, not
  wired into mobile or made into a public share feature.
- Signed URLs are **bearer capabilities**: anyone possessing one can fetch until
  expiry or object removal. Logout/project deletion immediately prevents new API
  access/link issuance, but cannot revoke an already-issued URL by itself. An
  in-flight response or downloaded copy cannot be recalled. Do not log, persist,
  publish or send signed URLs to analytics. TLS and access-log query redaction
  remain deployment requirements. This is intentionally different from the
  continuously authenticated API download route.

## Deletion and limits

Owner deletion commits the existing tombstone and revokes worker claims. Retryable
maintenance removes the canonical S3 project prefix (including losing attempts)
plus private-volume project/staging files. Access failures/partial deletion keep
`media_deleted_at` unset and the storage reservation charged. Repeated rescans can
remove late artifacts. Other owners/projects/prefixes are never deletion targets.

This increment **requires a private, nonversioned bucket**. API/worker startup
checks bucket reachability and versioning when S3 is selected. Cleanup rechecks
versioning and refuses both Enabled and Suspended buckets instead of falsely
claiming that DELETE removed historical versions. Do not enable versioning/object
lock without a reviewed version-aware erasure/retention implementation. Provider
bucket policies, Public Access Block, least-privilege identity scope and encryption
are operator-reviewed requirements, not automatically configured or certified by
this code. A nonversioned bucket alone does not establish privacy. Real local tests
prove anonymous denial for the configured test service, not every cloud provider.

Reservations are conservative admission budgets, not physical/object-store quotas.
Temporary assembly and transfer overlap can duplicate bytes. S3 operations have
connection/read/retry bounds, not a guaranteed whole-transfer wall deadline.
Rejected/replayed candidate prefixes get best-effort removal; crashes, an unknown
commit result, unavailable cleanup or hard-killed workers can leave orphans.
Unaccepted orphan reconciliation, abandoned upload retention, version/backups,
full account erasure, global capacity/egress budgets and alerts remain open.
No bucket-wide lifecycle deletion is installed; never apply a guessed lifecycle
that could remove accepted originals. No automatic migration of old local projects. Local inventory refuses to guess
unknown remote usage from empty scratch directories; remote inventory recovery
requires separate operator tooling.

**Direct signed upload/parts, remote staging, provider IAM roles/secret-manager
integration, strict worker egress isolation and fully stateless workers remain
next increments.** This first increment deliberately does not give clients PUT
capabilities that could overwrite already-verified chunks. All accepted media
must still pass the existing API's authenticated completion checks.

## Configuration and upgrade

Server-only variables (never `EXPO_PUBLIC_*`):

| Variable | Meaning |
|---|---|
| MEDIA_BACKEND | `local` default, or explicitly opt-in `s3` |
| S3_ENDPOINT | Internal API/worker S3 origin |
| S3_PUBLIC_ENDPOINT | Origin used for signed links; omit to use S3_ENDPOINT |
| S3_BUCKET | Existing private, nonversioned bucket |
| S3_REGION | Signing region; default us-east-1 |
| S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY | Scoped server S3 credentials from private settings |
| SIGNED_DOWNLOAD_SECONDS | 5–60, default 60 |

S3 mode requires explicit credentials; the adapter does not use ambient AWS
profiles, instance metadata or alter other SDK clients/the process environment.
Transport verification remains enabled. Staging/production endpoints must be HTTPS;
HTTP is permitted only for development/test localhost, 127.0.0.1 or Docker `s3`.
Default development Compose remains on local storage. No cloud secrets enter images.

For the owner's Windows install, stop API/worker/Expo, back up DB and media, then:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.txt
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
```

Keep MEDIA_BACKEND local for normal Pixel acceptance until a separate local S3
setup/provider configuration is reviewed. No additional storage inventory or mobile
npm install is needed solely for this increment. Do not downgrade/restore only the
DB after storing remote jobs: back up/restore media and reconcile both stores too.

## Reproducible isolated storage test

With Docker Desktop/Linux Docker and the project venv installed:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_object_store.py
```

Linux equivalent: `.venv/bin/python scripts/smoke_object_store.py`. The script pulls
the digest-pinned Apache-2.0 SeaweedFS 4.06 image, generates test-only credentials,
binds one random **loopback-only** port, creates one disposable local bucket,
starts its own isolated API/worker, runs real HTTP restart/resume/render/download,
checks anonymous denial, signed GET, forbidden PUT, signature tampering and actual
five-second expiry, then verifies deletion physically removed remote objects.
It limits test volumes to 64 MiB each (16 slots), and deletes only its own
container/anonymous data volume/config at exit; no existing volumes are touched.
Synthetic MP4s/reports/logs remain under ignored `.data/nextphase-s3-smoke-*/`.
The signature-expiry wait is included in reported workflow time; these are tiny
synthetic correctness runs, not production benchmarks. CI invokes this smoke;
remote CI success must be observed separately.

License metadata/notices: see LICENSE_AUDIT.md. Local server evaluation is not full
OS/container/transitive, cloud policy, patent, privacy or commercial legal clearance.

### CI startup diagnostics

The pinned image drops to seaweed UID 1000. The smoke copies generated 0600 config
into the created container's /data before starting it; the official entrypoint
sets data ownership. This avoids relying on the runner UID matching the container
UID and keeps the secret private. Early exit/readiness failure prints sanitized
server-log context. GitHub retains only the redacted server.log artifact for three
days; generated config and signed links must never be uploaded as artifacts.
