# Phase 2: upload rights acknowledgement and media input hardening

## Uploader acknowledgement

Before preparing a durable upload or sending its bytes, Create Short requires an
unchecked-by-default acknowledgement for the selected footage:

> This footage is mine or I have permission to upload and edit it, including permission from people shown or heard. I understand the video is uploaded for server processing.

Version: `upload-rights-v1`. Choosing a different file clears the checkbox. The
OS picker may cache the explicitly selected file locally before acknowledgement;
that is not a server upload or an automatic gallery scan. The durable private copy
and server transfer are gated by the affirmative choice. A saved acknowledged
intent retains its version for continuation after restart. Older saved intents
need an explicit confirmation; their key, private copy and server offset remain.
Stale screens cannot confirm/resume/discard a different newer pending intent.

Both upload APIs enforce the acknowledgement. A checkbox is not the sole guard:

- New `POST /api/v1/upload-sessions` JSON requires strict boolean
  `rights_confirmed: true` and `consent_version: "upload-rights-v1"`. Missing,
  false, numeric/string booleans or an unknown version return 422 before a new
  reservation is admitted.
- Legacy multipart `POST /api/v1/jobs` requires form strings
  `rights_confirmed="true"`, `consent_version="upload-rights-v1"`.
- Legacy multipart may spool request bytes before handler validation; acknowledgement
  is not an edge body limit or a replacement for transport resource controls.
- The server records version plus UTC receipt time on the upload session and
  copies them to its render job. The authenticated owner is already recorded.
  Exact replay does not restamp a current acknowledgement. Client-supplied dates
  do not become the record's timestamp. Session views expose these fields only
  to the owner; no new public/global rights endpoint is supplied.
- An old active session without acknowledgement cannot accept parts or complete
  until the updated client replays its original descriptor/key with confirmation.
  Rights fields are excluded from the immutable file/settings descriptor digest,
  preserving old keys and chunk offsets. Reconfirmation only stamps the existing
  active session. Completed legacy jobs/sessions remain accessible with unknown
  historical acknowledgement; migration never fabricates/backdates it.
- Discard remains possible without asserting rights. If the create response was
  lost before its ID was saved, `POST /api/v1/upload-sessions/discard-by-key` uses
  only the authenticated owner's Idempotency-Key to abort the existing session.
  If none exists, it commits a zero-byte, zero-budget aborted tombstone, without
  claiming rights or storing the video's name/title. This serializes with create
  and prevents late requests from resurrecting the discarded intent. No footage
  directory is created. New creation with that discarded key returns 410.
  Existing completion returns its original job for safe local cleanup. Network
  failure never permits removal of the saved private copy. Owner-only by-key GET
  is also available for metadata recovery; other accounts cannot read the session.

This is an authenticated **self-attestation**, not verification of ownership,
people's consent, legal age, privacy-law compliance or a licence manifest. It does
not authorize AI training, publication, voice cloning or third-party processing.
AI/provider calls and billing remain disabled. Moderation, verified asset rights,
privacy/terms review and formal retention/withdrawal processes remain required.
Unchecking stops a new/resumed submit; it does not undo bytes already accepted.
Use Discard/Delete for the implemented server-access/removal controls.

Acknowledgement metadata remains linked to operational/deletion records; no
complete personal-data erasure or legal evidence certification is claimed.

## Versioned baseline media profile

Server input profile: `baseline-media-v1`. The existing extension, 300 MiB source
and 600-second defaults remain; actual container/stream metadata is inspected.
The worker rechecks its source before rendering, including old queued jobs.
Accepted metadata must satisfy:

| Property | Limit/profile |
|---|---|
| Demuxers | MOV/MP4/M4V family or Matroska/WebM; extensions remain MP4/MOV/M4V/WebM |
| Video | Exactly one video stream; attached cover art and multiple video tracks rejected |
| Resolution | 16–7680 on either axis, at most 8,294,400 pixels per frame (UHD-equivalent budget) |
| Frame rates | Every usable average/nominal rate positive and <=120; at least one known rate |
| Audio | Optional single track, 1–8 channels, 8–96 kHz |
| Total streams | At most eight; unselected data/subtitle/attachment streams are ignored |
| Video codecs | H.264, HEVC, VP8, VP9, AV1, MPEG-4 Part 2, MJPEG |
| Audio codecs | AAC, MP3, Opus, Vorbis, FLAC, ALAC, selected 16/24/32-bit PCM variants (see media_policy.py) |

FFprobe and FFmpeg have explicit demuxer/decoder allowlists and **file-only input
protocols**. Remote/nested-playlist protocols are not enabled. The configured probe-size
parameter is 10 MiB (not a total file-read ceiling), analysis duration five media
seconds, and wall timeout remains 30 s.
A 64 MiB maximum **single allocation** and two codec threads bound selected resource
paths; filter/encoder threads are also two. These are not a total process-memory,
CPU/global disk quota or a guarantee against malicious codecs. Inputs whose
headers cannot be determined within these bounds fail safely rather than relax
protocol access. Existing output byte caps, cancellation and lease fencing remain.

Real tests cover H.264/MP4, HEVC/MOV, VP9/WebM and AV1, as well as a playlist with
an MP4 extension pointing to a local HTTP canary. Neither probe nor renderer
contacts it, including a simulated preflight/source-replacement race. Supported
codec metadata depends on the installed FFmpeg build; this is not licence/patent
clearance. No new codec binary/dependency or reference-kit asset was added.

High-speed/multitrack/professional formats may now be rejected. This increment
is not full phone-format/HDR/rotation/VFR normalization or intelligent reframing.
Metadata can be dishonest; bounded decode/render failure still remains possible.
File protocol access is not filesystem isolation: use patched, unprivileged,
restricted workers with OS/container memory/CPU/egress limits before real public
traffic. Antivirus, fuzzing/load/soak, complete sandboxing and production security
certification are still open. Final exports remain 9:16 and <=60 s, server-rendered.

## Windows upgrade and acceptance

Stop API, worker and Expo. Preserve actual DB/media backups, then from repo root:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-consent-media-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm run typecheck
npm run test:uploads
npm run test:auth
npm run test:exports
```

Migration `0009_upload_rights` adds nullable version/time columns only. Existing
accounts/sessions/media, storage inventories and completed downloads remain.
No new npm dependency, inventory rerun or sign-in is needed solely for this update.
Use updated API/mobile together; an old client missing acknowledgement fields
gets 422 on new creation and 409 on unacknowledged active-session parts/completion.
Do not force timestamps into old rows. Downgrade requires stopped services, prior
code and verified matching backups. Compose uses the ordinary stopped-service
backup/build/migrate/up sequence; keep its --no-proxy-headers API flag.

Physical Pixel acceptance is pending for this increment:

1. Open New Short: uploading is disabled until the acknowledgement is checked.
   Choose a different clip and confirm it clears. Do not assert rights for footage
   you do not own or have appropriate permission to edit.
2. Check it for a disposable consented clip, upload, pause/reopen/resume, render,
   Save to Photos and Share. New acknowledged intents should retain confirmation.
3. An older paused upload should ask once and resume from its existing progress;
   Discard should remain available without checking it. Do not clear app data.
4. A supported normal camera clip should still work. An unsupported format should
   give an error rather than hang or start phone rendering. Another project's old
   download and Delete should still work. Native UI/OS flow is not proven by mocks.

Private cloud storage, verified email recovery, full retention/legal policy,
observability/resource accounting and the remaining master roadmap gates stay open.
No paid service, cloud account or real billing was enabled.
