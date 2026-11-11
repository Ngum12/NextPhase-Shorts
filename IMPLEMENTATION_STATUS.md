# Implementation Status — 2026-11-10

## Reviewed candidate video preview pilot — 2026-11-11

The owner ran sentence-window-v2 on the saved generated-English/base-model
transcript, obtained two candidates and approved the highlighted text. Added
`scripts/preview_short.py` for an explicit operator acknowledgement and one numbered
candidate from the saved validated proposal. A private bounded source snapshot
must match its hash and probed duration before decoding. Fixed FFmpeg arguments
render only the selected range, 1080×1920/30-fps letterbox H.264/AAC (audio optional),
with frame-floor timing, actual frame-count/rate/duration/size QA, private reports,
no-overwrite admission, scratch cleanup and input preservation. Report hashes bind
source, proposal and output; actual audio/video meaning and cut review remain human.
No live API/worker/mobile entry point, captions/style/semantic claim, dependency,
restricted reference-kit asset, paid service or production rollout was added.
Staging/production and required-worker mode refuse the standalone pilot.

Validation: all 482 backend tests and 63 focused analysis/preview tests passed,
including real offset audio
verification, fractional-frame durations, a 60-second silent preview, mismatched/
invalid proposal rejection, private permissions, output preservation and cleanup.
The actual analysis-to-preview CLI demo produced a verified 442-frame/14.733333-s
synthetic preview. Synthetic manual annotations/tone are not ASR-quality evidence.
The owner's original generated-speech preview has not been rendered/viewed here;
the source remains on their VPS. See ANALYSIS_PILOT.md for operator commands.

## Disposable capacity CI database readiness — 2026-11-11

SQLite-matrix capacity CI failed before migrations with a closed published
PostgreSQL connection. Its local-socket `pg_isready` could accept the official
image's temporary init server before final TCP startup. Replaced that probe with
a bounded authenticated `SELECT 1` through the same host/published port/database
used by migrations, retrying transient connection/query errors. No migration,
burst, soak or restore assertions are disabled. On failure the disposable helper
retains only selected PostgreSQL state fields before cleanup; CI uploads that
small diagnostic, excluding full inspect/env/raw error text and DB contents.

Validation: 53 focused startup/planner/local-analysis tests passed. A real local
PostgreSQL capacity drill passed its 100-request burst (64 accepted, 36 expected
capacity refusals), 30-second synthetic soak (six render/download cycles), and
fresh-database restore with media hashes, owner isolation, deletion fencing and
a new render after restore. This short drill is not production load acceptance;
GitHub CI still needs to rerun on the pushed commit.

## Clean sentence-window search repair — 2026-11-11

Owner's verified base model ran on the VPS generated-English fixture and returned
35 words; its text improved over tiny, with one below-0.45 word (`stays`) and a
brand-name variation. Zero proposals prompted inspection: v1 tried individual
sentences or the furthest endpoint, missing shorter clean multi-sentence windows
when the longest one contained uncertain speech. v2 limits endpoints before the
next weak word/long gap, checks every start and uses prefix statistics for bounded
scoring. The threshold, whole-sentence, timing/frame/source and review guards stay
enforced. Regressions cover the weak-final-sentence case and a narrowly placed
clean region missed by the old sampling scheme.

Added saved-transcript replanning that preserves native provenance and words,
uses new private outputs and explicitly reports no new ASR execution. This lets
the owner retry the planner against the existing base transcript. Actual new
VPS proposals still require that retry; no recognition-quality, production
editing, rollout or paid-inference acceptance is claimed.
Validation: 48 focused transcript/local-analysis tests passed (one existing
Starlette warning). A saved French manual fixture was replanned through the CLI
with v2, four proposals and no ASR execution. Actual VPS base-transcript results
remain pending the owner's replan command.

## Native token inventory parser repair — 2026-11-11

Owner built the pinned CPU engine on the VPS and the official multilingual tiny
model passed its upstream SHA-1. The generated English speech test reached the
native parser, which rejected segment/token text agreement. Source inspection
of pinned whisper.cpp confirms that full JSON includes reserved timestamp tokens
such as `[_TT_100]`; the earlier text-spelling heuristic failed to remove those.
Parser filtering now matches upstream segment construction using vocabulary IDs
below EOT (50256 English-only / 50257 multilingual). It validates vocabulary/token
IDs, preserves ordinary text even if it resembles a control marker, and retains
spoken-text agreement, timestamp, confidence and duration checks. Added regressions
for native timestamp/language/extra markers and invalid IDs. Safe optional CLI
diagnostics report fixed classifications without transcript/native-log contents.
Real VPS inference/accuracy acceptance still requires the owner retry.
Validation: 45 focused transcript/analysis tests passed (one existing Starlette
warning), including the reserved timestamp-token mismatch reproduction and
English-only/multilingual EOT boundaries.

## Isolated transcript/planning pilot — 2026-11-11

Owner requested continued development after reviewing the app roadmap and left
the session. The latest private-VPS/phone/backup/alert evidence and remaining
external Phase 2 gates are consolidated in PHASE_2_ACCEPTANCE_2026-11-11.md.
Those gates are not marked closed; no live VPS, API, worker, schema or mobile
feature was activated by this prototype.

Implemented strict source-bound English/French word/transcript contracts,
bounded explainable sentence-window proposals with <=60-second/frame/source
checks, and an isolated local CLI producing private JSON/data-only EDL and an
interactive review page. Manual input is labeled manual; review is mandatory,
semantic quality is explicitly unverified and incomplete/low-confidence input
can yield no proposal. Untrusted transcript text remains inert browser data.

Optional local Whisper.cpp adapter extracts bounded mono 16-kHz WAV with the
existing file-only FFmpeg profile; verifies operator-trusted engine/model SHA-256;
uses CPU-only settings, credential reduction, parent-death/process/CPU/memory/file
limits and timeout cleanup. It refuses staging/production and required sandbox
worker mode. Native limits are not a replacement for tenant sandbox integration.
No model download, provider request, paid inference or customer-data transfer is
performed. The CPU engine built from pinned upstream v1.7.6 commit a8d002c and
its CLI flags were checked. Model-host access returned policy 403, so **real ASR
inference, speech accuracy, semantic quality and actual VPS analysis performance
remain unverified**. Executable protocol fixtures are not ASR evidence.

Synthetic-video/manual-annotation demos generated English/French proposals and
private review artifacts. Chromium exercised both pages, candidate highlighting
and selected-plan downloads: zero external requests and no JavaScript errors.
Actual FFmpeg audio extraction, source identity, nonfinite/overlapping timestamps,
duration/frame bounds, unsafe provider data, private output, overwrite refusal,
credential stripping and timeout cleanup have regression coverage. See
ANALYSIS_PILOT.md for reproducible commands, limits and next acceptance requirements.

Validation on this branch: baseline 414 tests passed; final full backend suite
**450 passed**, no skips, one existing Starlette warning (76.24 s). Baseline
HTTP/separate-worker FFmpeg smoke passed with owner isolation, 1080x1920/30-fps
4.9-second H.264/AAC/full decode and recovery/cleanup checks. Mobile TypeScript
passed. Both manual analysis demos and real browser candidate selection/EDL
downloads passed. No actual model inference or VPS analysis deployment is claimed.

## Automatic offsite backup preparation — 2026-11-11

Owner verified actual systemd backup/monitor service success, active 04:00 Rwanda
backup/five-minute timers and real alert test inbox delivery. Google Drive OAuth
remote was configured privately; the owner-supplied actual rclone upload of a
120-MiB encrypted scheduled bundle passed download checking with one matching
file and zero differences. No OAuth token was requested or committed.

Added opt-in `offsite-setup` that activates only after upload/readback, plus
automatic copies after a successful local backup/writer restart and a standalone
retry command. Only verified named ciphertext is eligible; local SHA-256 is
checked, remote writes are immutable/checksummed, and download checking must pass
before offsite status becomes true. Monitor/email report failed/stale copies.
No Drive synchronization/deletion or raw key/vault export is introduced. Existing
timers need no reinstall. Actual new integrated setup/job still requires VPS
validation. Independent immutable/current-journal custody, retention and external
host-down monitoring remain separate limitations.
Local validation: full backend suite 412 passed (one existing Starlette warning);
final focused maintenance run 20 passed, including offsite transfer/readback
failure, changed ciphertext, concurrent backup status and stale-copy alerts.

## VPS maintenance preparation — 2026-11-11

Actual-host scheduled-backup command subsequently passed authenticated readback
and copied-ciphertext hash verification; offsite copy remains false. Email setup
was saved privately, but its test returned HTTP 403/non-JSON. Added explicit
User-Agent/Accept request headers and fixed-field HTTP diagnostics to distinguish
API errors from edge filtering without printing provider bodies or credentials.
Actual sending success remains unverified until the VPS retry.

Owner reported trusted domain HTTPS readiness, unauthenticated jobs 401/docs 404,
and successful phone upload/render/Save/playback on the private VPS. An encrypted
120-MB backup authenticated/read back, restored into a new PostgreSQL test DB
(0020/23 tables), and matched SHA-256 after Windows transfer; test DB removed.
Owner reports an updated encrypted recovery vault/offsite copy. These are
owner-supplied actual-host results, not automatically recurring protection.

Added explicit maintenance commands and generated systemd timers: requested
04:00 Rwanda nightly local backup/readback and five-minute disk/readiness/worker/
certificate/freshness monitoring. Separate optional Resend failure email uses a
hidden key prompt and private files, with one-hour per-topic throttling and
explicit provider-acceptance scope. Automatic account mail remains off. No
timer installation, actual new scheduled backup or outgoing email is claimed by
the code change. Actual VPS execution/inbox/activation remain to be verified.
No automated offsite copy, retention deletion or independent host-down monitor
is implemented. Existing journal-rotation limitation remains unchanged.
Local validation: 405 backend tests passed (one existing Starlette warning);
The final focused run passed 12 maintenance tests covering writer recovery, busy queues, low disk, copied
backup hashes, notification throttling/recovery and timer generation. Systemd
calendar parsing and user-scope static unit verification passed; no units were
installed or started in the cloud environment. Generated VPS units still require
root-scope validation and actual execution on the selected host.

## Restricted domain HTTPS preparation

Owner supplied actual Contabo VPS evidence: Ubuntu 24.04, 4 CPUs, 8 GB RAM,
strict worker hostcheck ready, healthy private stack and all six
`vps_trial.py accept --synthetic` checks true. SSH key-only administrator access
and active UFW with SSH allowed were also owner-reported. These supersede the
earlier prospective-host status below; no public release is accepted.

Added an opt-in separate Caddy front door with persistent private certificate
state, one direct-client-IP restriction, hidden operator/docs routes and no
customer-data migration. Existing private services and operator TLS remain.
Local official SHA-512-verified Caddy routing checks passed allowed/denied peers,
forged forwarding headers, route exclusions and API forwarding; Compose validated
with required settings and refused missing settings. CI includes this routing
check. Actual ACME issuance, denied external network and phone HTTPS/upload/Save
remain unverified until run on the VPS. Public release stays blocked.

## Private VPS deployment preparation

Branch `dev/phase-2-vps-preparation`, based on merged main **fe22703**. Owner
selected a prospective Contabo 4-vCPU/8-GB/150-GB one-month trial; purchase and
provisioning are not claimed. No remote host credentials were supplied or used.

- Added a four-file private VPS trial overlay with dedicated Compose project/
  volumes, fresh database/session/broker credentials, loopback-only API/TLS ports,
  no published broker, bounded supervisor/database and one-render DB admission.
  Preparation is create-only, private and refuses unsafe links/permissions.
  Inherited PC env files, project/profile selectors and VPS interpolation values
  cannot silently select the working installation through the Python entry point.
- Added one acceptance command for actual worker containment, verified private
  HTTPS, monitoring and acknowledged operator delivery; explicit `--synthetic`
  then exercises the existing HTTP resumable upload/render/download/ownership flow.
  Private reports retain fixed failure codes and no raw command diagnostics or
  credential values. Missing prerequisites fail closed; no automatic init/restore,
  public exposure, mail sending, AI, billing or paid provisioning.
- Added `docs/VPS_DEPLOYMENT.md`: SSH access/recovery, fresh-only initialization,
  private tunnel preview, consistent encrypted transfer, independently current
  journal/key/checkpoint custody, old-host fencing and distinct before/after-write
  rollback rules. Trial uses local storage and APP_ENV=development explicitly;
  production S3/IAM, queue TLS, trusted mobile HTTPS, real budget feed, offsite
  recovery, human alerts and security/privacy/provider/legal acceptance remain open.
- **394 SQLite backend tests passed (78.09s)**, one existing Starlette/httpx
  deprecation warning. Includes five new deployment regressions and actual Compose
  resolution proving private ports, resource limits, fresh credentials and project
  isolation; no Docker engine/new application container is needed for that check.
  Final targeted deployment suite again passed **5 tests (0.16s)** after tightening
  local Docker selection, permissions and host-network refusal. Compilation, pip
  consistency and diff checks passed; no new dependency was needed.
- Complete real HTTP smoke passed: API restart/auth/refresh, interrupted 51-MiB
  resumable transfer/checksum/one-job publication, queue/render/download/decode,
  ownership, deletion/retention, telemetry/monitoring and worker crash/restart.
  Output **1080×1920 / 30fps / 4.9s**, baseline flow **2.01s**, not a load/SLA
  benchmark. Evidence `.data/smoke-cae4ed01bc8849d1aa66aaa1052f1ae3/`;
  mail companion used local MockTransport only, never Resend.
- The first smoke failed with a job still queued: free space was below the
  worker's configured reserve plus output allowance. That run is not a pass.
  Removed only two recognized generated 53,554,551-byte stress inputs and 186
  stale, structurally recognized pytest-only roots (about 187 MB total), retaining
  reports and all application volumes/data. The complete rerun passed with disk
  guards unchanged. No broad Docker pruning or resource-limit bypass.
- No mobile source/native/dependency change; prior owner Pixel acceptance remains
  valid, not relabeled as a new device test. No new PostgreSQL full-suite run or
  actual VPS/whole new Docker stack acceptance is claimed. Managed host still lacks
  enforced containment and has limited disk; guards were not weakened.

### Owner-reported consolidated activation now accepted

Owner supplied successful Windows activation after merging **fe22703**: consistent
PG/local-media safety snapshot, encrypted **13-file** bundle/authenticated readback,
private PKI with no runtime CA signing key, healthy stack, verified TLS readiness,
acknowledged operator delivery and actual rebuilt worker inventory (**292 OS / 47
Python packages**). This closes the earlier owner activation pending note below.
It is supplied owner evidence, not a cloud-executed Windows test or legal/image
vulnerability certification. No repeated activation or phone regression requested.

**Next:** review/merge this preparation; when the VPS exists, initialize only its
fresh private disposable trial and run its single acceptance command. Accept actual
host/performance results before reviewing real hosted configuration/data migration.
Phase 2 stays open for its remaining external gates; Phase 3 has not been started.

Implementation **d8eb579** pushed to `dev/phase-2-vps-preparation`. Automatic PR
creation returned GitHub GraphQL **Forbidden**; no PR number or remote CI success
is claimed. [Open the prepared review](https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-vps-preparation).
No PC pull/rebuild/device test is required before the VPS is available.

This is a **developer prototype**, not a production AI editor. Phase 0 engineering
validation and the server portion of Phase 1 are verified below. The owner has now
reported a successful physical Pixel upload/render/download test. This establishes
the reported Android baseline flow, not production readiness or AI functionality.

## Consolidated Phase 2 completion build — four areas, one review

Requested by owner to consolidate remaining backup, private deployment,
operations/cost and final-review work instead of further small PR/device cycles.
Branch `dev/phase-2-consolidated-acceptance`, based on merged main **bda9a56**.
Implementation **505035b** pushed. GitHub PR creation returned API **Forbidden**;
[open the consolidated review](https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-consolidated-acceptance).
No PR number or remote CI result is claimed.
**Local software acceptance is green; public/hosted release and Phase 2 remain
blocked on real external evidence/approvals explicitly listed below.** No paid
resource/API, real mail, billing, AI, DNS/public certificate or hosting activated.

Owner previously supplied protected Docker readiness and journal count **0 → 1**
with unchanged stream ID after actual sign-out. That closes the prior local journal
activation/write check; it is owner-supplied evidence, not a cloud-run Pixel test.
No mobile source/lock/native dependency changed here; no new phone regression
sequence or reinstall is requested.

### Built together

1. **Encrypted backups/recovery:** bounded streaming Fernet frames authenticate
   archive identity/order/finality plus file manifest hashes. Create-only private
   outputs, key exclusion, exact checkpoint/offline acknowledgement, changed-source/
   unsafe-path/link checks and low-disk guards. Recovery uses a NEW target,
   authenticates before extraction, rejects unsafe/duplicate members and never
   deploys a DB or replaces the current journal. Snapshot journal remains archival;
   the independent CURRENT journal/replay/release protects later deletions.
   Local media only: remote S3 objects/versions/provider state are not silently
   claimed backed up. Prior plaintext safety snapshots remain private and retained.
2. **Private deployment rehearsal:** pinned Caddy **2.11.9**, official archive
   SHA-512 verified, immutable Docker manifest digest. Real certificate-verified
   localhost HTTPS, private route/body/time/header controls, forwarded-IP defense
   and raw edge-request/error logging exclusion. Private CA/leaf and separate role
   credentials generated once; signing/backup keys stay in offline-only volume.
   Three-file Compose profile is loopback/private; actual cloud/IAM/certificate/
   queue-TLS/mobile trust remains a real deployment gate, not emulated acceptance.
3. **Operational/cost checks:** TLS-verified token-authenticated trace/coarse-alert
   delivery into a private bounded local archive/receipt sink; no human notification
   or full production collector claim. Source data includes no titles, credentials,
   raw URLs or arbitrary fields. Operator agent is role-separated, has no customer-media mount/direct external
   network and requests read-only DB transactions; media-disk measurement is
   explicitly not observed by that role, with API/worker guards retained. Provider-export reconciliation uses Decimal amounts,
   explicit coverage/freshness/approval, source hash and operator-controlled resume.
   Configured missing/stale/breached state pauses new admission/claims and emits a
   coarse alert; recovery/reads/deletion stay reachable. Actual provider costs,
   quotas/idle bills and human alert routing remain externally unverified.
   Staging/production requires budget configuration and rejects fixture mode.
4. **Final review/report:** one acceptance runner and explicit null external
   approvals template. Local software checks can pass while `release_ready:false`.
   Current PyPI/npm advisory checks and Caddy provenance/notice are recorded, not
   upgraded to complete OS/image/native/commercial legal certification.

### Actual verification

- **389 SQLite backend tests passed (85.43s)** through the combined runner and
  **389 PostgreSQL tests passed (102.55s)**; no skips, one existing Starlette/httpx
  deprecation warning each. Includes 21 new backup/control/review regressions.
- Complete consolidated command passed all five software checks: encrypted
  recovery, real private HTTPS renderer, monitoring delivery, budget admission
  gate and backend regressions. Final report
  `.data/consolidated-acceptance-81be9ac8cb6f44ca89aa0e2ec943568e/report.json`,
  with honest pre-commit dirty-tree flag/software hash and all external approvals
  false. CI now runs this as one SQLite acceptance step plus PostgreSQL regression/
  encrypted restore, not an owner-driven sequence of repeated small checks.
- Actual Caddy TLS test rejects an untrusted CA, verifies the trusted certificate,
  bounds body size, denies private routes on public listener, preserves rate
  limiting against forged forwarding headers, uploads/renders/downloads/fully
  decodes **1080×1920 output <=5s**, and proves sentinel query/header values do
  not enter proxy-failure logs. Worker-loss and budget-pause alerts are delivered
  and acknowledged; budget breach returns 503 for new upload with reads intact.
- Actual encrypted **PostgreSQL pg_dump → authenticated bundle → NEW database
  pg_restore → current-journal replay/release** passed, including old credential
  rejection, fresh local-only survivor recovery, retained output SHA and deletion
  cleanup. Evidence `.data/restore-journal-62b2e6e4f29b4ba5a84b8f56ec9856ca/`.
  Only fresh UUID databases on the existing local `_test` service were created
  and removed; no application database/container/volume was overwritten.
  SQLite encrypted counterpart also passed in the consolidated command.
- Official PyPI installed-version metadata: **52 packages, zero published
  findings, zero unavailable lookups**. Locked npm advisory refresh: **zero**
  info/low/moderate/high/critical findings. No new Python/npm dependency.
  These checks are narrower than full image/native/Go/OS advisory clearance.
- Combined Compose parse/read-back passed: loopback TLS, internal-only receiver,
  offline backup role, read-only DB/media/journal inputs and offline-key separation.
  Compilation, pip consistency and diff checks passed. Standard Nginx installer
  was unavailable (no sudo/helper); verified official Caddy was used and actually
  tested. No insecure TLS or package policy bypass.
- Managed Docker VFS disk remains too constrained for full rebuilt-stack execution;
  **Windows Docker activation script/actual new profile startup are the one owner
  host check**, not claimed executed by Linux/native tests. Existing services and
  data retained. Mobile's prior 70-test/TypeScript/export/owner acceptance is
  unchanged, not rerun/claimed new here.

### Final observer permission check

After removing the observer's media mount/direct external network, the final
SQLite suite again passed **389 tests (78.29s)** and the complete real Caddy TLS/
render/trace/failure-alert/budget/log-redaction rehearsal passed; evidence
`.data/private-staging-a2c5f57c577e418b93983ab1d0c547eb/`. A fresh isolated PostgreSQL
schema also passed actual monitoring/trace queries with
`default_transaction_read_only=on` and explicitly unobserved media-disk state.
That schema was removed; no application database or Docker layer was replaced.
The PostgreSQL full-suite result above remains the recorded 389-pass run, not
relabeled as a second full run for this observer-only adjustment.

### One review and one owner activation

After review/merge, finish uploads, pull and run
`scripts/activate_private_staging.ps1`. It privately snapshots current PostgreSQL/
local media, builds the roles, checks/creates private PKI once, encrypts and
read-backs a bundle without deploying the DB, starts the profile and checks TLS
readiness/acknowledged operator delivery. Failure stops; existing keys/volumes
are never reinitialized. Use all **three Compose files** afterward. Existing
USB/Expo Go HTTP loopback preview stays unchanged; private CA trust is not silently
installed on the phone. [Single runbook](docs/CONSOLIDATED_ACCEPTANCE.md).

Still required for actual hosted release: approved host/budget and quotas, actual
provider cost exports and human alert routing, externally trusted mobile HTTPS,
private S3/IAM/queue-TLS deployment, independent offsite key/current-journal/backup
custody and remote-version recovery, full license/native/image/security review,
controller/privacy/terms/provider approval and actual staging device acceptance.
These are **gates inside the four consolidated areas**, not new mini-phases or
waived risks. No claim that a local app admission stop halts provider billing.

## Phase 2 package 6 — independent journal and protected restore

Development branch `dev/phase-2-restore-journal`, based on merged main **e4789df**.
Implementation **d1e482a** pushed. Automatic PR creation returned GitHub API
**Forbidden**; no PR number or remote CI result is claimed.
[Open the branch for review](https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-restore-journal).
Owner reported the corrected SDK 58 Pixel selection/upload/render/save flow worked
very well. That is owner device acceptance, not a cloud-executed phone test.
Mobile source/lockfile unchanged in this increment; no repeated phone suite needed.

### Implemented

- Independent encrypted write-ahead account/project deletion and credential-change/
  revocation intentions. Existing cryptography Fernet plus domain-separated HMAC
  chain, stream/sequence continuity, canonical UUIDs, private owner-only files,
  no links/hardlinks, process lock and fsync. Five-second lock acquisition bound,
  64-MiB/100,000-record cap; missing/corrupt/full stream fails changes closed.
  No email/password/code/token/path enters journal payloads or public reports.
- Security requests record before their DB commit/HTTP success. Write-ahead intent
  can survive failed commits/replies; restore deliberately prefers conservative
  deletion over resurrecting data. No automatic reinitialization/repair after loss.
- **Migration 0020_restore_binding** adds explicit stream binding. Offline binding
  on the current stopped source bootstraps its existing deletion tombstones.
  Pre-activation/unbound snapshots are refused; removing/replacing a protected
  source's journal refuses API readiness/startup even in development. Never bind
  an old restored snapshot to pretend missing history is known.
- Offline preview verifies the stream and separately retained current checkpoint.
  Apply revokes all old sessions/refresh families/actions, cancels pending mail/
  active work/uploads, disables every surviving restored password and reapplies
  account/project tombstones including identities missing from the dump.
  Existing survivor completed media remains intact. Fresh recovery uses existing
  approved proof flow; no password/reset bypass or email service activation.
- Independent hold created before transaction, applied marker after commit;
  interrupted/failed replay keeps access blocked. API middleware blocks held
  traffic, liveness remains available. Explicit release requires successful replay,
  exact current checkpoint and a 120-second capability retirement interval.
  All old writers/hosts must be fenced; the offline flag is operator acknowledgement.
- Create-only, network-disabled local Docker init/overlay keeps journal/key in a
  volume independent of PostgreSQL/media. Root only owns the empty volume then
  drops to app user; no keys printed. Existing volumes are never overwritten.
  Staging API requires configured/bound protection. Independent offsite/immutable
  custody, separate production key vault/rotation and encrypted snapshots remain open.
- Disposable smoke environments now explicitly clear operator journal settings;
  they cannot append synthetic events to an operator's mounted stream.

### Validation and limits

- New focused suite: **18 passed**, covering concurrent encrypted append, changed/
  reordered/duplicated/partial/truncated/replaced/wrong-key streams, unsafe links/
  permissions, write/fsync failure without acknowledged DB changes, old-snapshot/
  missing/replaced stream refusal, existing-tombstone bootstrap, failed replay DB
  rollback/hold, all-credential retirement and native release timing.
- Protected HTTP drills on SQLite and PostgreSQL passed: snapshot BEFORE HTTP
  account/project deletion, password change and logout; independently current
  journal; NEW restored DB; replay/release; old access/refresh/password rejected;
  fresh local-only survivor recovery; exact retained output SHA preserved; deleted
  media cleanup verified. No real mail. Only stopped disposable fixture clocks
  were advanced for release/cleanup, never operator/production clocks.
  Bound evidence: `.data/restore-journal-ec2389d4ad0140dea02816726e7b485f/`
  (SQLite), `.data/restore-journal-3160e76b1b9c4fafbac461105ccddffd/` (PostgreSQL).
- Earlier complete suite at binding stage: **367 passed SQLite (89.04s)** and
  **367 PostgreSQL (105.54s)**. A later run including the final bootstrap test was
  interrupted by cloud disk exhaustion; final rerun results are recorded below.
- Docker's VFS exhausted the cloud disk during temporary container creation.
  Create-only init/user drop/key creation did succeed in one disposable container
  with current source/crypto on the older validation image; final unprivileged
  readiness/reinit and rebuilt overlay activation remain **pending host checks**.
  No new production image or strict containment acceptance is claimed. All owned
  temporary containers/volumes removed; existing development services preserved.
- Freed regenerable npm caches/cloud node_modules and synthetic resumable smoke
  videos to recover space. Source, lockfiles, test reports/logs, smaller outputs,
  user footage and application DB/media volumes retained. No new mobile test run
  is claimed after removal; prior 70-test/TypeScript/bundle plus owner Pixel
  acceptance remains unchanged. Tests use synthetic media only.
- No new dependency/license/API/provider, paid infrastructure, billing, AI, outgoing
  mail or public deployment. 9:16 and <=60-second server-render contract unchanged.

### Final regression results after disk cleanup

- **368 passed on SQLite (86.82s)** and **368 on PostgreSQL (105.73s)**,
  no skips, one existing Starlette/httpx deprecation warning per run. The final
  bootstrap, schema binding, hold and failure-path regressions are included.
- Complete baseline HTTP smoke passed after migration 0020: upload/replay/resume,
  owner isolation, auth/revocation, cancellation, server render, download/decode,
  deletion/retention, crash/restart, operations/monitoring; **1080×1920, 30fps,
  4.9s**, measured baseline **3.0s**. Evidence
  `.data/smoke-516bbc26b3b04df8925608a2ab4d8ca8/`.
- Bound PostgreSQL pg_dump/restore drill passed after correcting disposable PG
  readiness to require TCP (the initial Unix-socket readiness could observe the
  initialization-only server). SQLite bound drill and 18 focused tests passed.
- Compose overlay parse/read-back, py_compile, doctor, pip consistency and diff
  checks passed. Full rebuilt Docker overlay activation remains the disclosed
  host check; cloud disk limitations were not bypassed or called acceptance.

### Upgrade / next gates

Back up current DB/media, stop writers, rebuild updated services, migrate **0020**,
initialize independent local journal once and explicitly bind the current source
before new protected snapshots. Always include the journal Compose overlay after
activation. [Exact setup/restore runbook](docs/RESTORE_JOURNAL.md). Do not run replay
against the live account database as an upgrade test: replay intentionally locks
all credentials and requires recovery. Use the disposable drill/CI instead.

Local software restore protection is implemented; **Phase 2 remains open** for
immutable/offsite current journal/checkpoint/key custody, encrypted snapshot policy,
real deployment fencing/TLS/edge/private storage/collector/vault/cost ceiling and
security/privacy/licensing/provider approval. Manual DB rollback without the
protected procedure is not automatically detected; no universal erasure or DR SLA.

## SDK 58 Android picker/private-copy correction

Implementation **a1feb3e** pushed; this branch includes the Windows test fix.
GitHub PR creation returned **Forbidden**;
[open the combined fix for review](https://github.com/Ngum12/NextPhase-Shorts/pull/new/fix/sdk58-picker-copy).
Remote CI/native device results remain unobserved.

The owner supplied a Pixel screenshot showing `ExponentFileSystem.copyAsync`
rejecting the selected `cache/DocumentPicker` file as unreadable before upload.
Inspected installed SDK sources: Android DocumentPicker writes its cached copy
under the host context cache directory, while FileSystem experience permissions
reject that unscoped path in Expo Go. Switching only copy APIs would retain that
source-path issue; do not broaden permissions or bypass storage isolation.

- `fix/sdk58-picker-copy` includes the preceding Windows tooling assertion fix.
  Android now requests the user-granted document-provider URI with picker cache
  copying disabled. iOS retains its existing picker cache-copy behavior.
- Preparation awaits modern `File.copy` into the existing UUID private upload path
  before size validation/journaling. Subsequent resume reads only the durable
  private file. No base64/whole-video JS read, encoding, network fallback, broad
  gallery permission, arbitrary path rewriting or original-file deletion.
- Failed copy removes its incomplete private destination and creates no saved
  intent/server session. Copy errors now explain reselecting the video without
  displaying the native source path. Cancel preserves the existing selection;
  selecting again clears the previous error and requires rights reconfirmation.
- Added four adapter regressions: Android vs iOS picker options, cancellation,
  async provider-to-private copy/restart/resume without provider access, and failed
  copy cleanup preserving originals. These are not Android native execution.
- All **70 mobile/tooling tests passed**, including 20 upload/picker tests;
  TypeScript and Android Hermes export (3.1MB) passed. Physical Pixel provider
  permission/copy acceptance remains pending. Backend/schema/dependencies unchanged;
  no backend rebuild, migration, npm reinstall or paid service activation needed.
- After review/merge: pull, restart Metro on its actual forwarded port, **choose
  the video again** (the previous selection points at the inaccessible cache),
  acknowledge rights and check upload/pause/resume/render/Save/playback. Keep app
  data and originals; do not uninstall Expo Go or change media permissions.

## Windows SDK 58 tooling assertion correction

Implementation **ce97d3d** pushed. PR creation returned GitHub API **Forbidden**;
[create review from the branch](https://github.com/Ngum12/NextPhase-Shorts/pull/new/fix/windows-toolchain-paths).
No remote Windows CI result is claimed.

Owner upgraded merged main **145044a**: Docker API/database/queue healthy, worker
started, clean Windows npm ci reports **zero vulnerabilities**, TypeScript passed,
and **65 of 66** mobile/tooling tests passed. The sole failure compared native
Windows glob output `app\index.tsx` with a hardcoded POSIX `app/index.tsx`.
Metro started successfully on **8082**, which requires USB forwarding of 8082
in addition to API 8000. Physical SDK 58 acceptance is still pending.

- Dedicated branch `fix/windows-toolchain-paths` changes both async/sync traversal
  expectations to `path.join('app','index.tsx')`, preserving native glob behavior,
  ignore/version/cancellation checks and all production dependencies/application code.
- Added a focused Windows CI job on Node 24 for actual installed consumer tests.
  Its remote result is pending; Linux tests are not claimed as Windows execution.
- Local validation: both tooling checks, all **66 mobile tests**, TypeScript and
  diff checks passed. No backend changes, migration, dependency reinstall, server
  rebuild or repeated backend regression required for this assertion-only fix.
- Next: review/merge, `git pull --ff-only`, `npm run test:toolchain` from apps/mobile;
  keep Metro running and forward its actual **8082** port, then perform the existing
  focused Pixel navigation/upload/pause/resume/render/Save/play/Share check.
- Phase 2 staging/security/privacy gates remain open. No paid service, outgoing
  email, billing, AI or public deployment activated.

## Phase 2 package 6 preparation — dependency remediation and staging evidence

Review delivery: implementation **bf409a1** pushed to
`dev/phase-2-staging-blockers`. GitHub PR creation was attempted but the API
returned **Forbidden**; no PR number or remote CI result is claimed.
[Open the prepared branch for review](https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-staging-blockers).

Implementation on `dev/phase-2-staging-blockers`, based on confirmed main
**82f1ab1 / PR #24**. Resolves the largest concrete software advisory gate and
prepares remaining evidence; **package 6/Phase 2/public release are not complete**.
No paid resource/API, real mail, AI, billing, public hosting, domain/DNS change or
provider contract activation. Remaining engineering and owner/legal/provider gates
are mapped in [STAGING_BLOCKERS.md](docs/STAGING_BLOCKERS.md), not marked skipped.

- Coordinated official SDK map upgrade: **Expo 58.0.23, Router 58.0.30, React Native
  0.88.1, React 19.3.0**, SDK-matched modules/native peers and React types. Node
  engine matches Expo's supported range; owner's Node 24.15 is suitable.
- SDK upgrade removes the old decode/query, deepmerge and image-size chains.
  Upstream Expo CLI/fingerprint still declare glob 13/minimatch 10; **narrowly
  scoped reviewed overrides** select glob **14.0.4** for those two consumers and
  minimatch **11.0.5** for fingerprint. Existing PostCSS patch retained. These are
  tested consumer compatibility overrides, not a claim upstream Expo changed its
  declarations. No blanket override or `npm audit fix --force` was used.
- **Clean npm ci followed by fresh npm audit: zero findings**, down from 17
  (4 high/12 moderate/1 low). CI now checks the audit and real tool-consumer tests.
  This is advisory status for the locked graph, not universal security clearance.
- FileHandle chunk reads are awaited under SDK 58, with a Pause check before
  sending. Save explicitly imports `expo-media-library/legacy`; SDK 58's root
  deprecated function throws at runtime. Original/private-upload journal behavior,
  one bounded chunk, credential/origin isolation and separate Save/Share retained.
  No video rendering/inference moved to mobile.
- Docker API binding changes to **127.0.0.1:8000** by default for the existing USB
  workflow; LAN/public publishing now requires explicit review. No HTTPS/edge
  deployment or production network acceptance is inferred from loopback binding.
- Added create-only private `scripts/image_inventory.py`: selects an existing
  immutable local image ID (no pull), inspects installed OS/source/Python/FFmpeg
  metadata and copyright hashes without app env, secrets, mounts, network or DB.
  The result explicitly says vulnerability/legal scan not complete. Actual owner
  image still needs its own exact-artifact review; no false complete SBOM claim.
- Prepared an **unpublished privacy/preview terms draft** from implemented behavior,
  with exact missing operator/retention/provider decisions and honest deletion/
  backup limits. Asked only for registered company name/business country, never
  keys/account numbers. Missing owner/legal input is not assumed or waived.

### Verification

- Before upgrade: **63 app logic tests and TypeScript passed** on SDK 54.
- Clean SDK 58 install passed (545 installed npm packages). **64 app logic tests +
  2 real tooling-consumer regressions = 66 passed**, plus TypeScript. New test pauses
  during asynchronous reading and confirms no chunk send, closed handle and intact
  saved intent. Tool tests exercise CommonJS exports, async/sync traversal, ignore/
  case/dot matching and pre-aborted cancellation with patched glob/minimatch.
- Offline Expo compatibility check reports dependencies up to date, with its
  explicit offline validation warning. Real config introspection passed: Android
  broad read/location permissions remain removed, iOS has add-only photo text.
- Actual Expo fingerprint generation twice yielded equal 40-character hashes from
  **34 sources**. No customer media or secret content was printed/exported by this
  check. This exercises the real overridden consumer rather than an empty audit.
- Final clean-install Android Hermes export passed: **1,374 modules, 3.1MB**, 27
  assets. This is a JavaScript/native-config bundle, not a new APK, native SDK 58
  runtime/physical Pixel/iOS/performance acceptance.
- Fresh merged backend baseline **350 passed on SQLite (81.49s)**, one existing
  Starlette/httpx warning. Application backend/schema unchanged; PostgreSQL's prior
  350-pass evidence remains, not rerun/claimed new for this mobile/tools change.
- Complete HTTP upload/resume/auth/queue/server-render/download/cleanup/retention/
  monitoring/crash regression passed: **1080×1920, 30fps, 4.9s**, baseline **2.73s**.
  Evidence `.data/smoke-365a9c10909845c09700ea8a48f69b19/`. This confirms the service
  contract, not a native SDK 58 phone transfer or new S3 performance proof.
- Image inventory tested on the **existing earlier validation worker image**:
  292 OS/41 Python packages, private output mode 0600 and overwrite refusal passed.
  No app image was rebuilt or treated as the new production artifact. Compose
  parse/read-back confirms loopback API port; no running service was changed.
- Doctor, pip consistency and diff checks passed. No app/API migration. Mobile
  metadata inventory regenerated to **615** records; 29 direct/framework/tool/
  asset notice records preserved/indexed under `docs/licenses/sdk58*`.
  Material Symbols 0.4.53 navigation font (MIT wrapper/Apache-2.0 font) full notices
  and asset SHA/source retained; no restricted kit or stock media introduced.
  React Navigation's upstream MIT notice retained; exact fork asset revision is
  not independently established, remains in full transitive provenance review.

### Remaining gates / focused review

- **SDK 58 phone acceptance remains pending.** After review/merge, update Expo Go
  to SDK 58 compatibility (custom clients need rebuilding), npm ci, keep Docker
  running, restore USB forwards and do one navigation/login/reopen/pause/resume/
  render/Save/play/Share check. Do not uninstall/clear app data to hide migration
  problems; finish pending uploads and keep original footage. Native Expo Go
  storage behavior across SDKs is not guaranteed by adapter tests.
- Backend image/schema is unchanged: no repeated Docker image build/migration or
  owner full backend suite is required. `docker compose up -d` applies private
  port binding. Runbook: [STAGING_BLOCKERS.md](docs/STAGING_BLOCKERS.md).
- Still open: exact image/OS/native/transitive licensing/security scan; independent
  post-snapshot erasure/revocation journal and encrypted/offsite restore; approved
  TLS/edge/private-storage/queue deployment and scoped secret runtime; collector/
  alert delivery and real provider-cost ceiling/reconciliation; representative
  staging acceptance and privacy/terms/provider approval. These are concrete work
  and external decisions, not completed capabilities or legal risk waivers.
- [Unpublished draft](docs/PRIVACY_TERMS_DRAFT.md) needs registered operator/country,
  contacts/jurisdiction/providers and approved retention/rights decisions. No legal
  policy was published/accepted on the owner's behalf. Remote CI remains unobserved.
  Funding/credentials/public-domain exposure will require the existing approvals.

### Owner-reported package 5 acceptance — 2026-11-08

Confirmed merge **82f1ab1 / PR #24**. Owner backed up PostgreSQL, built the worker
and supplied updated strict host report: all three protections enforced, ready
true. Supplied monitoring status ok/no issues: three succeeded jobs/attempts, one
fresh idle worker/two stopped, no stuck/expired/missing claims, zero unknown or
inflight/stale intake records, local disk ok and 430,490,753 reserved bytes. Owner
explicitly confirmed latest Pixel save and playback. Existing one old measurement
gap and null rates remain expected. This is owner-supported host/device evidence,
not the unsupported managed cloud host or production/privacy/security signoff;
supersedes historical package 5 native acceptance pending notes below.

## Phase 2 package 5 — capacity, cleanup, restore and security disposition

Implementation on `dev/phase-2-capacity-security`, based on confirmed merge
**4c565b0 / PR #23**. Engineering locally verified for review; updated strict-host/
Pixel check and remote CI remain pending. **Public-launch security/privacy/license
blockers remain open**, listed below, rather than being waived or called complete.
Package 6 and Phase 3 have not been started. No paid infrastructure/API, real email
sending, billing, subscription collection or AI was activated.

- Migration **0019_global_capacity** adds a shared SQL admission mutex and bounded
  intake reservation records; preserves accounts/auth/media/jobs/trace/rights/
  upload offsets. Owner-then-global locking serializes collective slot/storage
  admission; processing claims have a global cap. Defaults 100 active, two
  processing, 50GiB logical retained budget. Existing accepted session conversion
  and same-key valid replay retain their prior semantics at capacity.
- Per-process request gate (default eight) avoids DB connection/thread starvation;
  waits asynchronously then returns retryable 503 after 30s. Shared intake limits
  cover count/bytes before multipart parsing; actual body/declared length/deadlines
  and local free-space guards apply. Unexpected API death leaves intake charged;
  stale recovery requires explicit stopped-writer assertion, not automatic reuse.
- Known failed/deleted media retains reservation until verified cleanup. Trace
  observations and stopped-worker pulses receive bounded seven-day maintenance;
  no automatic age deletion of valid saved projects, rights/cleanup tombstones or
  unverified orphans. Policy and full erasure limits are written explicitly.
- Strict Linux decoder write permission narrows from a directory to one precreated
  output file, with hard RLIMIT_FSIZE; probe has zero file-write size budget.
  Host canary checks allowed-file write and sibling creation denial. Real Linux
  file-size enforcement passed here; Landlock/cgroups remain unsupported on this
  managed host, so actual new strict render needs supported-owner-host acceptance.
- Added a disposable PostgreSQL HTTP load/soak/backup-restore exercise and CI's
  short version. It never accepts an existing API/database/media target. All its
  service processes/container/anonymous volume are cleaned; private synthetic
  backup/report artifacts remain ignored for review. No real owner's DB restored.

### Verification and evidence

- Unchanged isolated baseline: **339 tests passed (73.67s)**.
- Final complete backend suites: **350 passed on SQLite (88.81s)** and **350 passed
  on PostgreSQL (113.22s)**; no Linux skips, one existing Starlette/httpx warning
  each. Includes global owner/processing/storage/unknown inventory boundaries,
  crash reservations/free-space/body caps, bounded retention, kernel file limit
  and all prior migrations/auth/media/privacy/queue/storage regressions.
- **63 mobile logic tests and TypeScript passed**; no mobile source/native module
  changed and no new Android/Hermes build is claimed. Doctor, pip consistency,
  dependency inventory and diff checks passed. No repeated owner regression suite.
- **100 simultaneous real HTTP submissions** to disposable PostgreSQL: exactly
  **64 unique admissions, 36 intended retryable queue refusals**, same-key replay
  and cross-owner denial passed; recorded burst/check/abort interval **4.044s**.
  Eight active API executions bound DB use; this is not 100 renderers/transactions.
  Early preflights exposed pool starvation; request gating corrected it before
  final proof. Failed preflights are not reported as successful acceptance.
- **600.0-second real steady soak: 98 render/download cycles**, three rotating
  owners, two worker processes, synthetic two-second landscape/audio input;
  ownership/deletion checks passed. Not a production or mixed-codec/long-duration
  load benchmark, 24-hour soak or availability/security certification.
- Stopped all disposable writers, dumped PostgreSQL/custom format plus media,
  checked SHA-256 manifest, restored into a **fresh PostgreSQL database**, removed/
  replaced only original disposable media from backup; prior auth/output hash,
  deleted-project denial and **new render after restoration passed**. Evidence:
  `.data/capacity-exercise-3780e3279970/`. Short preflight also passed; CI uses 30s.
- Complete native HTTP restart/resume/auth/render/download/cleanup/retention/
  monitoring/crash regression passed: **1080×1920, 30fps, 4.9s**, baseline **2.59s**;
  evidence `.data/smoke-4787f8a97c784e8d97b86a8c0c7aee07/`.
- Complete **real Valkey/Arq plus private S3** regression passed under the new
  capacity/intake guards; signed direct transfer/expiry/sealing, AOF restart,
  render/download/decode, physical cleanup, account/auth/worker recovery and
  monitoring proofs passed. Same valid output; baseline **10.04s** includes signed
  expiry wait. Evidence `.data/nextphase-s3-smoke-180501389c97/workflow/` and
  `.data/nextphase-queue-smoke-58dfa85adf69/`. Standalone development guards are
  explicitly distinct from unsupported managed-host strict acceptance.

### Dependency/license/privacy review and remaining gates

- Fresh npm audit: **17 findings (4 high, 12 moderate, 1 low)**, unchanged. Router
  query decoding is potentially reachable; no blanket development-only dismissal
  or breaking SDK override. These are unresolved public-launch blockers.
- Official PyPI exact-version advisory JSON checked for **52 distributions**.
  Initial installer pip 25.0.1 had known advisories; updated isolated installer to
  **26.3**, pinned Docker/CI installer, verified zero published advisories for it.
  Final 52 checked versions have no listed advisories in that feed, not proof of
  absence of all vulnerabilities or a complete OS/wheel/static security scan.
- Metadata inventory remains **849**; pip version updated and packaged MIT notice
  retained. No new application dependency or restricted reference ZIP code/assets.
  Immutable image/OS/FFmpeg GPL/source-notice/patent/transitive review and legal/
  privacy signoff remain open. This managed environment did not rebuild a full
  application image or claim updated production-image scanning.
- [Security risk disposition](docs/SECURITY_REVIEW_2026-11-08.md) explicitly blocks
  public launch pending supported dependency remediation/approved mitigation,
  production containment check, image/legal review, real global/provider quotas/
  cost reconciliation, encrypted offsite backup and post-snapshot deletion/
  revocation journal. Local restore proves pre-snapshot tombstones only; missing
  later erasure requests cannot be reconstructed from that backup alone.
- Trace/stopped-worker aging is not full personal metadata erasure; crash records,
  accounting/rights/grant/tombstones/backups/provider/device copies remain scoped.
  Logical budgets/free-space checks are not an S3 quota, entire disk inventory or
  provider billing stop. Longer representative staging load/soak and edge/TLS/
  connection controls remain package 6 gates. No owner risk waiver was requested
  or inferred from permission to implement this package.
- After review/merge: active PostgreSQL/media backup, rebuild, updated hostcheck
  ready true, migration 0019, one Pixel render/save/playback and aggregate monitoring
  check. See [capacity/security runbook](docs/CAPACITY_SECURITY.md). Native Windows
  adapters do not establish the changed strict Linux output-file policy.

### Review delivery

Implementation **cfbc42e** pushed to `dev/phase-2-capacity-security`. GitHub
GraphQL returned **Forbidden** when automatic PR creation was attempted; no PR
or merge is claimed created here. Manual review link:
https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-capacity-security .
Remote CI/new supported-host/Pixel acceptance remain pending. Public-launch
security/privacy/legal blockers remain OPEN regardless of review/merge.

### Owner-reported package 4 acceptance — 2026-11-08

Owner merged PR **#23**, backed up PostgreSQL and rebuilt the Docker stack. Supplied
monitoring report: status ok/no issues, two successful jobs/attempts, one fresh idle
worker/one stopped, zero expired/missing claims, no truncation. One new render had
8.059s attempt wall, 7.686s encode, 14.83 lower-bound decoder CPU seconds and
330,002,432 maximum sampled RSS bytes; download/ingress measurements present.
Prices were unset/null; one older job lacked new spans/artifact measures, expected
historical unknown coverage. Owner explicitly confirmed Pixel save and playback.
These are supplied host/device results, not independent cloud-agent device tests;
remote CI and external collector/vault/provider reconciliation remain unobserved.
This supersedes package 4's historical owner-check pending notes below.

## Phase 2 package 4 — monitoring, secrets and measured-cost coverage

Implementation branch `dev/phase-2-monitoring-secrets-costs`, based on confirmed
merged main **017bf20 / PR #22**. Locally verified for review; owner check and
remote CI remain unobserved for this package. Packages 5–6 have not been skipped.
No paid service/API/infrastructure, real email sending, AI, billing or public
monitoring endpoint was activated.

- Additive migration **0018_observations** preserves users, passwords, sessions,
  projects, media, upload offsets/rights, claims and broker state. It adds nullable
  job trace/parent IDs, fixed-schema observations and known-artifact measurements.
  No historical resource/byte/cost values are fabricated or backfilled.
- API admission → queue/attempt/encode/QA/publication correlation uses server-created
  trace IDs. Retries retain the job trace and separate attempt spans. Authorized
  downloads bind to the project trace; earlier resumable-part requests have their
  own request traces/aggregate bytes rather than invented per-job attribution.
  Broker payload remains strict JSON containing only the generation UUID.
- Monotonic stage wall times, Linux decoder CPU lower-bound/sampled maximum RSS,
  derived encode throughput and observed API/worker storage bytes. These are not
  exact CPU, true peak memory, instant progress or TCP/client-save confirmation.
- Bounded private OTLP/HTTP JSON and Prometheus text exports, local queue/failure/
  liveness/truncation/optional cost alerts and explicit CLI exits. Create-only
  private UTF-8 export files refuse overwrite. No external collector, network
  exporter, scheduler or alert recipient was configured or contacted.
- Monetary defaults remain **null**. Explicit validated USD rates estimate observed
  attempt allocation, known original/successful-output lifetime and API/storage
  transfer components, with sample counts/partial per-job P50/P95 and missing
  coverage. Cost thresholds alert on observed estimates, not total provider spend.
  Direct signed traffic, failed transfers, staging/orphans/backups, idle/API/DB/
  broker costs and provider fees/taxes remain unknown and clearly reported.
- Mounted `_FILE` secret adapter for JWT/DB/S3/broker/Resend/mail keys rejects
  ambiguity, links/junctions, unsafe file types/permissions, oversize/multiline input.
  Values are not printed or copied into decoder environments. Reports show source
  type only. Rotation runbook covers restart, deliberate JWT re-login, retained
  mail decrypt keys, broker coordination and external provider revocation. No cloud
  vault provisioning or provider/IAM rotation is claimed.
- Raw Uvicorn target/query access strings are replaced with fixed content-free
  request events. Unexpected request errors return sanitized 500 responses without
  exception payload/traceback. Existing lost-commit recovery tests retain durable
  source/offset/one-job checks under that safe HTTP failure contract. Decoder import
  remains independent of validating server secrets. Telemetry loss is best effort,
  emits fixed warnings and never rolls back accepted work.

### Verification

- Clean unchanged baseline snapshot: **317 backend tests passed (70.08s)**.
- Final complete suites: **339 passed on SQLite (81.71s)** and **339 passed on
  PostgreSQL (101.67s)**, no Linux skips, one existing Starlette/httpx deprecation
  warning each. Includes real decoder correlation/resource/byte measurement,
  nested failure privacy, rates/known-lifetime exact arithmetic, unknown/truncated
  coverage/alerts, secret-file failure/rotation and additive migration preservation.
- **63 mobile logic tests and TypeScript passed**; no mobile source/native/dependency
  change or new Hermes/device build is claimed. Doctor, pip consistency and diff
  checks passed. No dependency added; 849-record inventory and notices unchanged.
- Complete local HTTP restart/auth/resume/upload/queue/server-render/download/
  deletion/retention/crash checks passed; observed baseline **2.33s**, output
  **1080×1920, 30fps, 4.9s**. Monitoring companion checked stage/resource/byte data,
  actual private OTLP export and explicit unknown/no-price reporting. Evidence:
  `.data/smoke-d504714de8e843ac9bad8cd639e0baef/`.
- Complete **real Valkey/Arq + private S3** regression passed, including AOF hard
  restart persistence, signed direct transfer/expiry/sealing, actual render/save
  download/decode, remote cleanup, account/worker/auth proofs and new monitoring
  export/counters. Same valid output; observed baseline **9.56s** includes signed
  expiry wait and is not a capacity/SLA benchmark. Evidence:
  `.data/nextphase-s3-smoke-61692c11f142/workflow/` and
  `.data/nextphase-queue-smoke-a73ecd24c02b/`.
- An earlier full S3 run completed the render/monitoring checks but later failed
  creating a disposable account fixture due to disk exhaustion; it is not counted
  as a full pass. Removed only 31 exact known generated 53,554,551-byte resumable
  stress inputs from agent smoke directories, reclaiming 1.66GB. Reports, result
  videos, application volumes and unrelated data were preserved; complete rerun
  then passed. No production stack was rebuilt on the unsupported managed host.

### Explicit remaining gates and focused acceptance

- Review/merge and remote CI; then rebuild the owner's existing Docker stack,
  perform one Pixel render/save and run `docker compose exec -T worker python -m
  app.monitoring --check`. See [runbook](docs/MONITORING_SECRETS_COSTS.md). No repeated
  owner regression suite is required. Back up the **active PostgreSQL DB/media**;
  the earlier Windows SQLite backup does not back up the Docker database.
- External collector/alert routing, real secret-manager mounts/IAM revocation and
  provider billing/physical-inventory reconciliation require the reviewed staging
  environment and approved rates/credentials. They are not claimed complete by
  this local export/adapter. No secret value needs to be supplied in chat.
- Observation/operational metadata retention/global admission, complete storage/
  egress cost coverage, representative load/soak/restore/security and production
  hard cost ceiling remain the explicit packages 5–6 gates. Last-known 17 npm
  advisories, complete OS/transitive license/security and privacy/legal review
  remain unresolved. No external protocol collector acceptance or total cost/
  production security certification is inferred from passing local tests.

### Review delivery

Implementation commit **41d67f9** pushed to `dev/phase-2-monitoring-secrets-costs`.
Automatic PR creation was attempted; GitHub GraphQL returned **Forbidden** in this
environment, so no PR/merge is claimed created here. Manual review link:
https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-monitoring-secrets-costs .
Remote CI and focused package 4 owner acceptance remain unobserved.

### Owner-reported package 3 acceptance — 2026-11-08

Confirmed PR **#22** merged at **017bf20**. Owner supplied Docker Desktop worker
build and host report: unprivileged user, cgroup limits, filesystem/network
isolation all **enforced**, **ready: true**. Full Docker DB/broker/API were healthy;
worker and supervisor started, `/ready` returned true. Operations snapshot showed
one succeeded job/attempt, one fresh idle worker, zero expired/missing claims and
status ok with no issues. Owner explicitly confirmed Pixel save and playback worked.
These are owner-supplied host/device results, not this managed host's containment
or cloud-agent device execution. This supersedes package 3's historical host/device
pending notes below; managed kernel/runtime remains unsupported, remote CI unobserved.

## Phase 2 package 3 — durable queue and worker supervision

Implementation branch: `dev/phase-2-queue-reliability`, based on merged main
`06e5c86` (email delivery PR #21). **Implemented and locally verified; strict host
acceptance, review, remote CI and the focused owner device check remain open.**
No package 4 work, paid infrastructure/API, billing or AI was activated.

- Chosen stack: pinned Valkey 8.1.11 and Arq 0.28.0; PostgreSQL remains the
  authority for fair scheduling, attempts and publication. Migration 0017 adds
  transactional dispatch signals, reconciliation, hard deadlines and dead letters;
  preserves existing media/accounts/uploads and the two-attempt reservation budget.
- Authenticated durable AOF broker uses strict bounded JSON, fixed functions and
  canonical generation IDs, with no pickle, customer payload or secret in messages.
  Lost replies, broker restart and duplicate delivery reconcile against SQL state.
- Claims renew every 10 seconds within a 45-second lease and fixed hard deadline.
  Expired/superseded claims cannot revive or publish. Transient failures use bounded
  retry/backoff; exhausted/permanent failures receive explicit dead-letter records.
  Deletion respects older attempt hard deadlines before releasing media/storage.
- Decoder controls include process-tree teardown for both FFmpeg and FFprobe,
  stripped credentials, unprivileged execution and required Linux filesystem/network
  isolation plus cgroup checks. Unsupported required protections fail closed.
- Compose includes private broker configuration and a separate supervisor. The
  helper preserves credentials without printing them. The isolated broker service
  was verified healthy, unprivileged, read-only and capability-dropped, then removed.

### Automated evidence

- Final backend suite: **317 passed on SQLite (74.01s)** and **317 passed on
  PostgreSQL (88.54s)**; one existing Starlette/httpx deprecation warning each.
- Mobile: **63 logic tests passed** and TypeScript passed; no mobile code changed.
  No new Hermes export or physical-device acceptance is claimed for this package.
- Full HTTP upload/queue/render/download: database adapter, real Valkey/Arq adapter,
  and Valkey plus private S3 all passed. Output verified **1080×1920, 30 fps, 4.9s**;
  observed render waits 2.05s, 3.52s and 9.79s respectively, not a load benchmark.
  Broker smoke also verified AOF restart persistence and duplicate/lost-reply recovery.
- Evidence (ignored local artifacts): `.data/smoke-64b6ddaa9d254d408753d2e1753a7bc1/`,
  `.data/nextphase-queue-smoke-be933caa2219/workflow/`,
  `.data/nextphase-queue-smoke-84c3c8ae6bc4/` and
  `.data/nextphase-s3-smoke-59d99fc9bedd/workflow/`.
- Actual seccomp network-denial test passed. Landlock tests verify refusal on this
  unsupported kernel; their passing result is **not** successful filesystem isolation.
- Dependency inventory now has 849 records; Arq/redis/hiredis MIT notices and Valkey
  BSD-3-Clause notice retained. Full container OS/legal review remains open.

### Blockers and next steps

- **Strict Linux host acceptance is OPEN:** this managed host returns ENOSYS for
  Landlock and Docker reports cgroup driver `none`. The focused host report returns
  `ready: false`. No production guard was bypassed to claim acceptance.
- After review/merge, follow [QUEUE_RELIABILITY.md](docs/QUEUE_RELIABILITY.md): run
  the single host check and share its coarse report. On a supported host it must
  report `ready: true`; then perform one focused Pixel upload/render/save check.
- This is shared-kernel isolation, not a VM/security certification or per-job disk
  quota. Capacity/soak, broader security/cleanup, deployment, privacy/legal and
  production acceptance remain in packages 4–6. Existing mobile audit findings
  (last observed 17) are not declared resolved by this queue change.

### Review delivery

Implementation commit `7fc90d2` was pushed to `dev/phase-2-queue-reliability`.
Automatic PR creation was attempted but GitHub's GraphQL API returned Forbidden
in this environment. The branch is available for review; create the PR at
https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-queue-reliability .
Remote CI and merge are not claimed observed. Host acceptance remains open.

### Owner-reported package 2 acceptance update

The owner reports real inbox verification, password reset, new-password sign-in
and upload/render/save worked, then disabled mail sending again. This records
owner acceptance, not an independent provider observation. Real sending stays
opt-in; no recipient, key or mail content is recorded here. Earlier package 2
notes below describe the state at its implementation and are retained as history.

## Phase 2 package 2 — optional Resend delivery and verified-email policy

- Implementation on `dev/phase-2-email-delivery`, based on confirmed merge
  **f200dc3**. Owner selected Resend, reports `auth.techskillnow.com`/DKIM/Forge
  records verified in Ireland and a sending-only API key prepared privately.
  No key was shared with this environment. Dashboard/DNS verification is an owner
  report, not an independent real-provider/inbox acceptance observation.
- **Real sending remains disabled by default and no real email was sent here.**
  No paid API/infrastructure, subscription billing or AI activated. Optional Resend
  adapter uses fixed HTTPS origin, verified TLS, no redirects, bounded IO/reply
  handling and a stable per-outbox idempotency key with a frozen message body.
  Provider terms/current free limits/Forge/idempotency behavior could not be checked
  from this environment (provider-site proxy Forbidden); account review remains.
- Migration **0016_email_outbox** adds method-tagged actions, encrypted outbox and
  persistent attempt budgets. It preserves legacy local proof meaning/accounts/
  passwords/sessions/uploads/jobs/media. Action hash and encrypted envelope commit
  atomically; no best-effort background gap for real delivery. No plaintext proof
  or recipient is stored in outbox columns; existing users.email remains account
  data. Envelope binding/expiry/credentials/deletion are checked before dispatch.
- Separate mail sender: owner-first locks, 90-second fenced leases, crash recovery,
  <=5 attempts, backoff/Retry-After, permanent failure states and no raw provider
  errors/log payloads. Network calls hold no owner lock. Concurrent senders share
  UTC day/month caps and one reservation/second. Defaults 20/day, 500/month; QA
  helper 5/day, 20/month, one owned recipient. Reservations/retries/crashes count
  conservatively, not provider billing units. Other apps' quota is not included.
- Accepted/terminal ciphertext is removed immediately; <=1,000-row maintenance
  wipes expired payloads and removes metadata after expiry plus one day. Existing
  render auth maintenance also cleans mail. CLI supports private aggregate reports,
  cleanup and bounded/cursor-based key re-encryption. Separate Fernet key ring,
  backup/rotation procedure; loss of keys fails those messages closed. No wall-clock
  purge SLA while processes are stopped; provider copies/backups/inboxes are outside
  this cleanup. Password/reset/deletion cancel queued/claimed mail transactionally;
  an already in-flight send may arrive, but its proof is revoked and completion fenced.
- Opt-in `AUTH_REQUIRE_VERIFIED_EMAIL` gates multipart upload/session creation/
  parts/completion/direct grants/commits. Only method `resend` from an accepted
  outbox establishes trusted verification. Local proofs cannot be promoted or
  redeemed across channels. Login/refresh/recovery/deletion, existing-project
  reads/downloads and abort/discard remain available; previously queued renders
  may finish. Default preview policy remains false until reviewed real-channel QA.
- Mobile distinguishes disabled/local/real delivery, avoids claiming delivery
  from generic request acceptance, displays actual verification state and blocks
  upload/resume with a route to confirmation when policy requires it. Paused upload
  state is preserved. No permission/native module/mobile key added.
- Baseline **264 tests passed (49.15 s)**. Final **294 backend tests passed on
  SQLite (57.25 s) and PostgreSQL (70.62 s)**; no skips, one existing Starlette/
  httpx warning each. Covers atomic encrypted issuance/failure, secret-free generic
  requests, concurrent/stale claims, exact retry bodies/keys, network/4xx/5xx/rate
  failures, caps/clock reversal/max attempts, payload/key/expiry cleanup, reset/
  deletion races and refresh revocation, trusted-upload routes and additive legacy
  proof migration. Extended existing live decoder check separately passed: new
  RESEND_API_KEY/AUTH_MAIL_ENCRYPTION_KEYS are stripped from child environments.
- **63 mobile logic tests**, TypeScript and Android Hermes export passed:
  **1,016 modules / 2.73 MB**. Offline Expo check reports dependencies up to date,
  with its explicit offline-validation limitation; this is not a new registry audit.
  Doctor/pip consistency/diff checks passed. Compose email profile parses correctly;
  it was not deployed or claimed to have enforced production host limits.
- Full local HTTP upload/resume/queue/server-render/download/operations/deletion/
  retention/crash/auth regressions passed: 1080×1920/30 fps/4.9 s, baseline **2.00 s**.
  Evidence: `.data/smoke-731512b82ea541daad99303c41783f70/`. Separate real HTTP API
  plus mail-process fixture restarted API before sending, killed sender after mock
  provider acceptance, advanced only its stopped disposable lease and recovered
  the exact message. Verification admission, one-use reset/all refresh revocation,
  other-owner isolation, ciphertext removal and secret-free logs passed. **Transport
  was local MockTransport only, not Resend.** Private temp data was removed.
  Evidence: `.data/email-delivery-smoke-0e9f3487bb2946168505e337cc71b6a5/` (standalone
  earlier proof `.data/email-delivery-smoke-e29b097bd18b443d817c9b9c39881d2f/`).
- Private S3/direct-upload full regression also passed, same valid output, baseline
  **8.02 s** includes signed-link expiry wait; staging/original/output cleanup and
  separate mock email proof passed. Evidence:
  `.data/nextphase-s3-smoke-126d8547688f/workflow/` and
  `.data/email-delivery-smoke-d0fd93af96374bfbbc0c1902c708d117/`.
  Normal smokes force real email/enforcement off regardless of inherited settings;
  full smoke/CI includes the explicit disposable mock proof.
- Added pinned cryptography **50.0.2**, installed cffi **2.1.1**/pycparser **3.12**;
  packaged license notices preserved and metadata inventory regenerated to **846**.
  No restricted reference-kit code/assets. Existing last-known 17 npm advisories,
  full dependency/OS/wheel audit and legal/privacy signoff remain open; metadata
  review is not commercial production clearance.
- Private setup helper uses a hidden terminal key prompt, preserves encryption
  keys, atomically saves ignored local configuration and leaves sending/policy off.
  Upgrade requires Python requirements installation, backup/migration 0016 and
  restart. Runbook [EMAIL_DELIVERY.md](docs/EMAIL_DELIVERY.md) specifies one owned-
  inbox Pixel verification/reset/upload/save check under conservative free-plan
  caps, then restores disabled preview settings. No repeated manual test suite
  requested. Remote CI/actual provider/inbox/Pixel/privacy acceptance remain pending;
  package 2 is **not closed** and package 3 has not been started. Production cgroup
  host enforcement remains open and was not bypassed. No production deployment.
- Delivery: implementation **7e12d27** pushed to `dev/phase-2-email-delivery`.
  GitHub GraphQL returned **Forbidden** creating the review PR; no PR or merge was
  performed here. Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-email-delivery

## Owner acceptance and package 2 preparation

- Confirmed upstream main **f200dc3**, merge of PR **#20** (session refresh).
  Owner reports all five focused Pixel checks passed: fresh sign-in, app reopen,
  access renewal after the 70-second check, upload/resume/render/save, and sign-out/
  sign-in. These are owner-supplied device results, not independent observations.
- Package 1 local automated proof remains 264 SQLite/264 PostgreSQL tests, 61
  client logic tests, TypeScript/Android export and full HTTP/private-S3 workflows.
  Remote CI lookup returned GitHub API **Forbidden**; its status is unobserved,
  not passed. This gate remains explicit rather than being silently dropped.
- Started `dev/phase-2-email-delivery` from the confirmed merge. Inspected current
  auth-mail/actions/client capabilities: only disabled/private local-file delivery
  is implemented; no durable real-delivery outbox, SMTP/provider or verified-email
  policy is present. Package 2 is not complete. Its preparation checklist is in
  [EMAIL_DELIVERY_PLAN.md](docs/EMAIL_DELIVERY_PLAN.md).
- Asked only for provider/sender-domain names (or a request for a recommendation),
  never passwords/API keys. No configured environment secrets are available.
  Delivery stays disabled; no real email/provider, paid resource or billing was
  activated. No runtime code/dependencies/schema changed in this acceptance note;
  only documentation verification is required, not another device regression run.

## Fixed remaining Phase 2 scope — package 1 session refresh

The owner approved the [six-package checklist](docs/PHASE_2_CHECKLIST.md), in order,
with one review and focused native acceptance where needed. This is the current
remaining scope; older increment notes below are historical evidence. Packages
2–6 remain pending: real delivery, queue/host enforcement, observability/secrets/
costs, capacity/security and staging. No blocked gate is waived; no Phase 3 started.

- Implementation: `dev/phase-2-session-refresh`, based on merged main `295428d`.
  Migration **0015_refresh_sessions** adds hashed grants, absolute-expiry families
  and nullable indexed access-family linkage. Existing accounts/passwords/access
  sessions/media/uploads remain preserved. Sign in once for refresh credentials.
- New access default 15 minutes, refresh idle seven days/absolute 30 days.
  Owner-locked rotation, domain-separated keyed hashes, shared IP/token budgets
  and default 120-second same-key response recovery. Different-key reuse commits
  family revocation before 401; matching late retry fails without revoking newer
  credentials. Other login families survive. Theft of both old token and key
  permits recovery within the bounded window; this is not device identity proof.
  Old access remains valid until its short expiry after normal rotation.
- Logout-current/refresh logout revoke family access; logout-all, password change,
  reset and account deletion revoke every owner family atomically. Consumed refresh
  grants support logout even with expired access and remain to absolute expiry
  for replay detection. Maintenance removes <=1,000 expired families per batch,
  with grant count dependent on activity; global metadata limits remain package 5.
- Mobile uses one versioned SecureStore pair/retry intent, persistence before
  sending/using replacements, single-flight refresh and serialized storage.
  Stale replies cannot overwrite/borrow newer account credentials. Stable UI
  generation handles prevent rotation cancelling uploads. GET/native download
  retries once; writes/multipart are not replayed. Offline failures retain intent;
  definitive refresh 401 requires sign-in. All-device logout requires server
  confirmation. Direct S3 transfers remain free of API credentials/cookies.
- Baseline **248 backend tests passed (46.72 s)**. Final **264 tests passed on
  SQLite (57.87 s) and PostgreSQL (67.83 s)**, no skips, one existing Starlette/
  httpx warning each. Covers rotation/retry/reuse, concurrent same/different keys,
  logout scopes, password/reset/deletion revocation, idle/absolute/access expiry,
  secret-free validation/rate limits, consumed-hash retention/cleanup and additive
  legacy-session/password preservation, plus all prior regressions.
- **61 mobile logic tests**, TypeScript and SDK alignment passed, including
  expiry single-flight, restart/lost-reply journal, failed intent/replacement writes,
  stale login/rejection/write races, logout confirmation, legacy restore, API-origin
  isolation, native download renewal and prior upload/direct-S3/auth regressions.
  Android Hermes export passed: **1,016 modules / 2.73 MB**. These are adapter and
  bundler checks; no new physical Pixel/Windows/iOS acceptance is claimed.
- Full local HTTP upload/resume/queue/render/download/operations/retention/deletion/
  crash regression passed: 1080×1920/30 fps/4.9 s, baseline **1.83 s**. Evidence:
  `.data/smoke-ea385da976844feab4c572a00a8f714f/`. Separate real HTTP refresh proof
  restarted API after rotation, recovered exact pair, rejected different-key
  reuse, preserved another login and revoked via consumed refresh. It checked
  secret-free logs and temporary DB cleanup. Expired-access proof signs a past-
  expiry fixture JWT; it does not change a live application's clock/DB. Evidence:
  `.data/session-refresh-smoke-ad0d6094ca834f798b5627824c26036b/`.
- Disposable private S3/direct-upload full workflow also passed, same valid output;
  baseline **8.03 s** includes signed-link expiry wait. Original/output/staging
  cleanup, retention and separate local recovery/refresh proofs passed. Evidence:
  `.data/nextphase-s3-smoke-73deceeadf11/workflow/` and
  `.data/session-refresh-smoke-6500659d9505424eaa9bb83e95fb9761/`.
  Backend CI includes refresh proof via full smoke; mobile CI adds refresh tests.
  `npm test` now runs every client regression script in one command.
- Doctor, pip consistency and diff checks passed. No dependency/native module,
  reference-kit source/assets, email sending, paid API/infrastructure or billing
  activated. Existing 843-record inventory and last-known 17 npm advisories remain
  unresolved; no new security/license/privacy clearance is claimed.
- **Package 1: locally verified; review/remote CI/focused Pixel acceptance pending.**
  Runbook: [SESSION_REFRESH.md](docs/SESSION_REFRESH.md). Stop/back up/migrate/
  restart, sign in once, then one local short-expiry/app-reopen/upload/save/sign-out
  check. No repeated manual regression suite requested. Production cgroup-host
  acceptance remains package 3; managed Docker driver `none` was not bypassed.
  No production deployment performed.
- Delivery: implementation **`faf0fa7`** pushed to `dev/phase-2-session-refresh`.
  GitHub GraphQL returned **Forbidden** when creating the review PR. No PR or merge
  was performed here; owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-session-refresh

## Phase 2 increment — local authentication recovery proofs

- Migration **0014_auth_actions** adds expiring one-use action hashes, HMAC
  account/credential binding and nullable method-tagged email-proof fields.
  Existing accounts are not backfilled as verified or locked out. Login/upload
  verification enforcement remains false. No dependency or native module added.
- **Real email delivery remains disabled/unimplemented.** The sole opt-in adapter
  writes a private local inbox only for development/test; staging/production
  reject it. No SMTP/provider request, funded infrastructure or email send occurred.
  local_file proof is not evidence of real-world email ownership and must not
  become production verification authority. Public confirmations are unavailable
  by default; there is no unauthenticated reset bypass or API-returned debug code.
- Requests use uniform generic acceptance for known/unknown/failed/disabled
  delivery, with shared IP/email rate limits. Local preparation runs after the
  response; action commit precedes private atomic message publication. This is
  best-effort development delivery, not a durable production outbox. File failures
  invalidate undelivered actions without logging email/code/path/exception text.
- Reset requires a 256-bit random 5–30 minute proof and commits password update,
  competing-proof consumption and all-session revocation together. No JWT or
  automatic login is returned. Owner locking serializes competing resets and
  password/deletion races. Email confirmation records only local method/time.
  Password change/reset/delete invalidate pending proofs; re-registering an email
  cannot recover the deleted owner. Expired DB proofs are cleaned in <=1,000-row
  batches by auth maintenance; private local message files require operator cleanup.
- Mobile adds Forgot password and Account local email confirmation with clear
  disabled/test-only copy, secure inputs and no persisted code/password. Public
  requests send no bearer/cookies and do not expire another login on failure.
  Post-reset validation uses existing originating-token guards. Auth 422 validation
  responses now avoid echoing input passwords/codes. No new permissions/API keys.
- Baseline **233 tests passed (44.68 s)**. Final **248 tests passed on SQLite
  (58.37 s) and PostgreSQL (68.52 s)**, no skips, one existing Starlette/httpx
  warning each. Covers private opt-in/production rejection, uniform requests,
  secret-free validation/delivery failures, hashed proofs, purpose/expiry/single
  use, parallel competing resets, revoked sessions/changed credentials/deletion,
  private-folder restrictions, bounded expiry cleanup, commit-before-publication
  and additive legacy-account/password preservation, plus all prior regressions.
- TypeScript and **44 client logic tests** passed (seven new recovery tests plus
  prior 37). Android Hermes export passed: **1,016 modules / 2.72 MB**. Tests use
  adapters; no new native Windows/Pixel/iOS acceptance is claimed. Doctor, pip and
  diff checks passed. No new dependencies/assets: existing 843-record inventory
  and last-known 17 npm advisories remain unresolved; no new legal/audit clearance.
- Real private local HTTP proof restarted the API with a pending reset code,
  confirmed one-use reset/same account, old-session revocation, other-account
  preservation, credential-change invalidation, local method tagging, secret-free
  access logs and complete temporary inbox/DB cleanup. Default full HTTP and S3
  workflows keep delivery disabled, then run this separate disposable file fixture.
  No actual email address was contacted and no existing account DB was modified.
- Full HTTP upload/resume/queue/server-render/download/operations/deletion/retention/
  crash regression passed: 1080×1920/30fps/4.9 s, baseline 2.32 s. Evidence:
  `.data/smoke-4566f84040ef475aa001d13ac92cac29/` and
  `.data/auth-recovery-smoke-d18726c45d804f3ab8d399bec84f25b0/`.
  Disposable private S3 workflow also passed, baseline 7.95 s includes six-second
  signed-link expiry wait; same valid output, original/output/staging cleanup and
  separate local email-action proof. Evidence:
  `.data/nextphase-s3-smoke-fe4e1e45c3c4/workflow/` and
  `.data/auth-recovery-smoke-df26a060b0f84306a945816c121739bb/`.
- Owner-reported merged operations acceptance (`80d7d0e`): migration current,
  **230 Windows tests passed, three expected Linux-only skips (190.70 s)**; full
  S3-backed smoke passed (baseline 4.41 s; `.data\smoke-4783d10e820f4468820cfa22cdd7c028`).
  Windows hard termination correctly had zero stopped records in that fixture;
  stale classification used only the documented synthetic observation clock.
  Subsequent live readiness returned true, operations status ok, one fresh idle
  worker, zero expired/missing claims. Owner then confirmed listed Pixel upload/
  render/save checks. These are supplied results, not independent device tests.
- Upgrade: stop API/workers, back up DB/media, migrate 0014, restart server and
  Metro; no pip/npm reinstall needed solely for this build. First verify disabled
  behavior; optional file QA uses a disposable account and private operator inbox.
  Never paste codes/messages into chat/issues/screenshots or expose that folder.
  Runbook/protocol/retention boundaries: [AUTH_RECOVERY.md](docs/AUTH_RECOVERY.md).
- Remaining Phase 2: owner-approved real email delivery, verified-channel policy,
  durable encrypted outbox/cleanup/notifications, refresh/MFA, broker/lease renewal,
  per-tenant isolation/egress, monitoring/retention, load and privacy/legal signoff.
  Strict Docker cgroup-host acceptance remains open (managed driver none); it was
  not bypassed. Paid services, AI and billing remain disabled; remote CI and new
  native acceptance remain unobserved. No production deployment performed.

- Delivery: implementation `3181744` pushed to `dev/phase-2-auth-recovery`.
  GitHub GraphQL returned `Forbidden` creating the PR; no PR, merge or production
  deployment was performed. Manual owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-auth-recovery

## Phase 2 increment — operational visibility

- Migration **0013_worker_pulses** adds minimal per-process liveness metadata:
  random worker ID, start/last/stopped times, interval and sampled phase. No user,
  host, PID, media reference or credential is stored. Existing accounts/projects,
  media paths, upload intent/offset/rights records are preserved; no dependencies.
- Worker heartbeat thread uses its own short DB sessions during foreground work.
  Default 10 seconds (allowed 1–60), fresh for three intervals plus 15 seconds;
  stopped/future-clock/stale states are distinct. It **never renews job leases**
  or proves render progress. Hard kills retain last-seen until stale; orderly
  stops mark the process stopped. Old process metadata remains retained, not GC'd.
- GET `/ready` returns minimal no-store DB/schema availability (200/503), with
  no raw exceptions or operational counts; `/health` remains unchanged liveness.
  Compose API health now uses readiness. Provider reachability, worker capacity,
  driver timeout tuning, overload/edge hardening remain separate boundaries.
- Private `python -m app.operations` reports current nondeleted job states, oldest
  queue/processing ages, expired/missing deadlines, bounded recent worker states,
  windowed attempt states and fixed failure codes. Unknown labels are grouped as
  other. It exports no IDs, names, paths, titles, URLs or secrets. No public
  metrics/admin route. `--check` returns 1 for attention, 2 for unavailable DB/schema;
  otherwise reports are read-only and never mutate retries/deletion/leases.
- Worker lifecycle/render/recovery/outage events are validated JSON with fixed
  messages and narrow fields. Canonical job/process correlation UUIDs remain in
  private logs; arbitrary payloads, user IDs, URLs, tokens and exception text are
  rejected. Legacy maintenance/third-party lines may remain plain. No complete
  distributed tracing/exporter, external alert delivery or global log certification.
- Baseline **220 tests passed (44.46 s)**. Final **233 tests passed on SQLite
  (53.41 s) and PostgreSQL (61.91 s)**, no skips, one existing Starlette/httpx
  deprecation warning each. Coverage includes concurrent pulse advancement without
  lease mutation, shutdown/nonresurrection, DB retry privacy, worker truncation/
  skew, queue/failure privacy, CLI exits, readiness failures, JSON log guards and
  additive migration preservation. Final strengthened pending-upload/rights/key
  preservation assertion also passed separately on both DBs.
- TypeScript and all **37 client logic tests** passed. No mobile source/native
  change or new APK/device test claimed. Doctor, pip, Compose syntax and diff
  checks passed. No paid API/infrastructure, monitoring provider, AI, billing,
  reference-kit code/assets or production deployment. Existing 843-record license
  inventory and last-known 17 npm advisories remain unresolved, not newly audited.
- Real isolated HTTP upload/resume/render/download/deletion/retention/crash smoke
  passed (1080×1920/30fps/4.9 s; baseline 2.02 s). Readiness, fresh/advanced worker
  pulse, operator CLI snapshot and two structured render events passed. After its
  own writers stopped, the fixture observed stopped state, detected a synthetic
  expired claim with CLI exit 1, and classified no fresh workers with an observation
  clock advanced 200 seconds. No real waiting-period or production lease change.
  Ignored synthetic evidence: `.data/smoke-28b154327dcf424f9ca6bc0adde279be/`.
- Disposable private S3 direct-transfer/sealing/render/download/signed-expiry and
  cleanup smoke repeated the operational checks successfully. Output 1080×1920/
  30fps/4.9 s, baseline 7.99 s includes six-second signed-link expiry wait.
  Evidence: `.data/nextphase-s3-smoke-e24b6eaf0ab0/workflow/`.
  Initial new smoke assertions incorrectly expected retained successful jobs after
  project deletion; corrected them to distinguish current queue state from retained
  successful attempt history. No pass was claimed for those initial failed runs.
- Owner-reported post-fix Windows acceptance on merged `9f294fd`: complete S3-backed
  smoke exited zero (baseline 2.95 s), temporary SQLite cleanup passed, and owner
  then confirmed listed Pixel old/new project, upload/render/save/cancellation
  checks passed. Evidence: `.data\smoke-ce8a9b04c0844fedbf74ebc8bc649c5c` and
  `.data\worker-recovery-93f7ad0561f84fc58cd72bb52129360b`. No newer Windows pytest
  count or independent remote CI success was supplied. These are owner reports.
- Strict Docker cgroup enforcement remains unsupported in this managed runtime
  (driver none), as previously reproduced; the guard was not disabled. No rebuilt
  production stack or new enforced-resource claim. Private CLI/heartbeat data is
  a bounded observation, not a capacity/progress SLA. Remaining Phase 2: broker/
  lease renewal, per-tenant isolation/egress, alert/exporter/retention policy,
  verified auth recovery, global capacity/load/soak and production security/legal.
- Upgrade/runbook: [OPERATIONS.md](docs/OPERATIONS.md). Stop API/workers, back up
  DB/media, migrate 0013, restart updated processes and check readiness/private
  report. No npm/pip reinstall needed solely for this build. Native Windows/Pixel
  and strict Docker-host acceptance of this new increment remain outstanding.

- Delivery: implementation `0942d9d` pushed to `dev/phase-2-operations`.
  GitHub GraphQL returned `Forbidden` creating the PR; no PR, merge or production
  deployment was performed. Manual owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-operations

## CI follow-up — procfs process-exit race

- Owner supplied a failed PostgreSQL GitHub Actions run: **213 passed, one
  failed (85.68 s)**. The hard-worker-crash test raised ProcessLookupError
  reading `/proc/<pid>/stat`; it did not establish that FFmpeg survived. The
  kernel can remove a process after procfs open but before read (ESRCH), while
  the old observer handled only FileNotFoundError on open (ENOENT).
- Test observer now treats both specific exit conditions as stopped. Regression
  cases retain live-process detection, zombie handling and propagation of other
  errors such as permission failures. No blanket OSError suppression, relaxed
  kernel containment assertion or retry-to-pass behavior was added.
- Child readiness waits for complete marker JSON, not just the creation of an
  empty/partial file. A deterministic partial-marker regression covers that
  adjacent CI scheduling race. These changes affect tests only, not production
  process supervision, queue behavior or resource limits.
- **220 backend tests passed on SQLite (55.02 s) and PostgreSQL (60.92 s)**,
  no skips, one existing Starlette/httpx warning each. The 21 targeted resilience
  tests passed (3.91 s), and the actual Linux hard-crash/credential-stripping test
  passed **ten consecutive independent runs**, stopping immediately on any failure.
- No application/mobile/schema/dependency change. HTTP/S3 smoke and native device
  tests were not repeated for this test-observation fix. Existing validation and
  strict Docker cgroup/Windows-native acceptance limits remain as recorded below.
  No paid infrastructure, API, billing, AI or reference-kit assets introduced.
- After review/merge, assess the **new GitHub Actions run for the fix commit**;
  rerunning an older commit does not validate the fix. Remote CI success has not
  been observed by this agent. No local reinstall, migration or app change needed.

- Delivery: `d0d3d12` pushed to `fix/ci-process-exit-race`. GitHub GraphQL
  returned `Forbidden` creating the PR; no PR/merge was performed by the agent.
  Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/fix/ci-process-exit-race

## Windows follow-up — worker smoke temporary SQLite cleanup

- Owner merged worker resilience (`f7fd233`) and reported **209 Windows tests
  passed, three expected Linux-only skips (410.52 s)** and TypeScript passed.
  HTTP/S3 upload/render/download/deletion/retention and crash/restart checks ran,
  but the overall smoke exited nonzero: WinError 32 removing its temporary SQLite
  database. This is not recorded as a complete Windows smoke pass. No new Pixel
  or strict Docker cgroup acceptance was supplied.
- Root cause: closing ORM sessions returned SQLite connections to the engine
  pool; the helper kept those idle file handles open until process exit. Linux
  unlink permits this, while Windows correctly refuses removal of the open DB.
- The disposable helper now registers engine disposal with ExitStack, which runs
  before TemporaryDirectory cleanup on success or exception. Child termination
  still precedes disposal. Success/report output is deferred until the temporary
  directory is confirmed absent, and includes `temporary_cleanup=passed`.
- Two real-subprocess regression cases simulate Windows refusal with any idle or
  checked-out pooled connection: both normal completion and an injected error
  after DB use pass. The same guard fails against the original helper with
  "SQLite pool still holds file handles", reproducing the defect on Linux.
- **214 backend tests passed on SQLite (51.01 s)**, no skips, one existing
  Starlette/httpx warning. Standalone crash/restart smoke and complete HTTP smoke
  exited zero, validated 1080×1920/30fps/4.9 s output, and confirmed temporary
  cleanup. Baseline flow 2.97 s; ignored synthetic evidence:
  `.data/smoke-dd76299e5eaf48909554e4b6db9a900b/` and
  `.data/worker-recovery-a50ac41cb65c40128f3f936117dfc769/`.
- Native Windows rerun remains outstanding; Linux simulation is not claimed as
  Windows execution. PostgreSQL, S3-specific and mobile tests were not repeated
  for this fixture-only fix; prior results and the owner's new reports remain
  scoped as above. No application code, schema, dependencies, media policy,
  resource guard, paid service, AI, billing or license asset change.
- After review/merge: pull and rerun `python scripts/smoke_e2e.py` from the root
  with the existing venv/server configuration. No migration or reinstall needed.

- Delivery: `0857f57` pushed to `fix/windows-worker-smoke-cleanup`. GitHub
  GraphQL returned `Forbidden` creating the PR; no PR or merge was performed.
  Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/fix/windows-worker-smoke-cleanup

## Phase 2 increment — fair queue and worker containment

- Eligible accounts rotate by durable most-recent attempt claim, never-served
  accounts first, retaining FIFO inside each account and existing concurrency/
  disabled-account guards. Retries consume a turn. PostgreSQL keeps SKIP LOCKED;
  this is turn fairness, not equal CPU time, paid priority or Sybil resistance.
- Expired-job recovery now handles at most 100 jobs per pass (maximum 1,000),
  retaining state/expiry fences and the two-attempt cap. SIGINT/SIGTERM cooperates
  with rendering and expires only its own processing claim after teardown.
  DB loop failures retry without logging raw exceptions. No broker, heartbeat,
  immediate crash detection or exactly-once claim; unexpired static leases remain.
- FFmpeg/FFprobe environments omit server credentials, Python search overrides
  and proxy/provider configuration. Linux exec launcher enforces parent-death
  SIGKILL, zero core dumps, 128 descriptors and a bounded CPU rlimit; POSIX render
  groups are killed/reaped. Fixed media policy, wall/output limits and 9:16 <=60 s
  output validation remain. Discarded diagnostics avoid unbounded FFmpeg stderr.
  Windows development retains direct execution/cooperative cancellation; hard
  Windows worker death can leave a decoder, and three Linux-only tests are skipped.
- Compose adds init, read-only root, no capabilities/new privileges, 64-MiB /tmp,
  two CPUs, 2-GiB memory and 128 PIDs. Its worker requires actual cgroup v2 limits
  and fails before DB/queue work if missing/excessive. Standalone development
  defaults the guard off. No per-tenant filesystem/network sandbox or production
  hostile-code isolation is claimed; shared media/provider access remains trusted.
- **Runtime blocker, explicitly reproduced:** managed Docker reports cgroup
  driver none and memory/CPU/PID support false. Container view is outer 32 GiB,
  four CPUs, unlimited PIDs. A bounded synthetic container render, UID 1000,
  read-only root, zero capabilities and no-new-privileges passed, but requested
  worker cgroup ceilings cannot be verified/enforced here. The final worker
  correctly refused startup with the required-limit error before queue work.
  Strict Docker Desktop/Linux-host acceptance remains open; no guard bypass for
  production or claim that this managed host enforces those resource ceilings.
- Baseline **197 tests passed (32.87 s)**. Final **212 tests passed on SQLite
  (45.76 s) and PostgreSQL (52.01 s)**, no skips, one existing Starlette/httpx
  deprecation warning each. Covers fairness, bounded recovery/expiry/fencing,
  shutdown/outage behavior, actual hard-parent-death/process-group/CPU termination,
  credential reduction and fail-closed cgroup validation, plus prior regressions.
- Bounded burst: 100 synthetic submissions, ten accounts, up to 16 in flight;
  exactly 30 admitted/70 capacity refusals and three fair ten-account rounds.
  This is not 100 simultaneous renders, a long soak or a production SLA/capacity
  benchmark. Existing multi-process claim/cancellation/deletion races also passed.
- TypeScript and all **37 client logic tests** passed. Mobile code/dependencies
  unchanged; no new APK/Android export or independent device acceptance claimed.
  Doctor, pip, image build, Compose syntax and diff checks passed. No migration:
  existing **0012** remains current. No new dependency/provider/reference-kit asset,
  paid API/infrastructure, AI, billing or production deployment. Existing 843-record
  inventory and last-known 17 npm advisory/legal/security gates remain unresolved.
- Final isolated HTTP smoke passed restart/auth, 51-MiB interrupted/resumed upload,
  render/download/decode, deletion and offline retention. Output 1080×1920/30fps/
  4.9 s, baseline 1.79 s; ignored synthetic evidence:
  `.data/smoke-60a71d5a130d4c4b9d744858ee976b08/`.
  New disposable worker proof kills its claimant, advances only that killed fixture's
  lease, restarts another worker and validates real output plus stale publication
  refusal and two attempt records. No real production lease-wait observation.
- Final disposable S3 direct-upload/restart/sealing/render/download/signature/
  deletion/retention smoke passed (1080×1920/30fps/4.9 s; baseline 7.96 s includes
  six-second signed-link expiry wait). Synthetic evidence:
  `.data/nextphase-s3-smoke-9aa313fd5786/workflow/`. Worker crash/restart evidence:
  `.data/worker-recovery-d18ebac09e394c03978ef25d8f48d08e/` (local) and
  `.data/worker-recovery-7e263137861c4568b0fafb1b03999755/` (S3-run companion;
  that companion deliberately uses its own local fixture, not remote crash I/O).
  Sanitized container observation is `.data/worker-container-proof.log` (ignored).
  CI triggers include the new crash helper; remote CI remains unobserved.
- Validation initially hit disk exhaustion; no failed checks were reported as
  passes. Removed only regenerable 51-MiB synthetic stress inputs from prior smoke
  runs, unused build cache and two unreferenced worker image revisions. Application
  volumes/running services and reports/logs/result videos were preserved; checks
  reran successfully after space recovery. Final container-limit refusal is an
  expected safety check, separate from that earlier disk failure.
- Owner-reported merged account-deletion acceptance (`b2caa0e`): migration current,
  197 Windows tests (125.34 s), TypeScript/37 client tests and S3-backed smoke passed
  (baseline 5.31 s; `.data\smoke-a36a31c3ab1a47dcb4a8fe68e5a4e7b2`). Owner confirmed
  all listed disposable-account Pixel checks worked. These are supplied reports,
  not agent-executed device or kernel-limit verification.
- Upgrade/Windows versus Linux behavior and precise remaining limits:
  [WORKER_RESILIENCE.md](docs/WORKER_RESILIENCE.md). Stop/restart native services;
  no npm/pip installation or migration change is needed solely for this build.
  Docker must rebuild/recreate and pass enforcement checks first. Remaining Phase 2:
  strict host acceptance, broker/heartbeat, per-tenant sandbox/egress, global capacity,
  representative load/soak, verified auth recovery, observability and legal review.

- Delivery: implementation `dcd54ea` pushed to `dev/phase-2-worker-resilience`.
  Automatic PR creation returned GitHub GraphQL `Forbidden`; no PR, merge or
  production deployment was performed. Manual owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-worker-resilience

## Phase 2 increment — account deletion and recoverable confirmation

- Migration **0012_account_deletion** preserves live accounts and adds durable
  disablement/receipt/cleanup metadata. Password-confirmed deletion atomically
  revokes every session and render claim, tombstones projects/uploads and scrubs
  account email/password and media display/path fields. Owner-lock rechecks stop
  late admission, upload publication and worker claims after disablement.
- Mobile adds Delete account with explicit confirmation and current password,
  plus Finish account deletion on sign-in. A private random SecureStore receipt
  recovers lost replies after authentication revocation. Server stores its hash,
  offers only coarse status for seven days, rate limits recovery and never uses
  the key as account login. Only confirmed deletion clears that owner's pending
  private upload; network/local cleanup failures retain recovery state. Original,
  saved/shared videos, caches and other account data are preserved.
- Worker maintenance durably retries/resweeps canonical disabled-owner local and
  S3 prefixes after upload/lease/grant deadlines. Namespace mismatches, unsafe
  owner links and I/O failures stay pending. Operational tombstones, fingerprints,
  rights/cost/session/grant records, historical untracked stores, versions and
  backups are outside full erasure. No production privacy-compliance claim.
- Baseline **187 tests passed (30.19 s)**. Final **197 tests passed on SQLite
  (37.79 s) and PostgreSQL (45.66 s)**, no skips, one existing Starlette/httpx
  deprecation warning each. Regression coverage includes
  additive migration, session revocation, wrong password/rate limits, receipt
  secrecy/expiry/collision, fenced completion, concurrent late upload admission,
  pending-part/budget cleanup, namespace/provider failures and owner isolation.
- TypeScript and **37 client logic tests** passed (15 uploads, 9 auth/API,
  7 exports, 6 account recovery). Android Hermes export passed: 1,014 modules,
  2.70 MB. Native/network adapters are mocked; no new Pixel/iOS acceptance claimed.
- Real isolated HTTP smoke passed upload → queue → server render → download,
  restart/auth, resumable transfer and previous deletion/retention checks. Output
  1080×1920 / 30 fps / 4.9 s; baseline 2.43 s. Evidence (ignored synthetic only):
  `.data/smoke-a8c66e5939e645dc9dad13e9f4a504c5/`.
- Disposable local S3 smoke also passed direct transfer, verified sealing, render,
  signed download expiry and orphan/project cleanup (baseline 8.14 s includes
  six-second expiry wait). Evidence:
  `.data/nextphase-s3-smoke-e696b31a83c0/workflow/`.
  Both runs additionally disabled a separate synthetic account over HTTP,
  restarted its API, recovered its receipt and verified revocation/other-owner
  preservation. After stopping their own writers they advanced only the synthetic
  cleanup deadline and verified local/S3 owner-media removal. This does not claim
  an actual waiting-interval observation or deletion of the owner's real account.
- Doctor, pip and diff checks passed. No new dependency, proprietary kit code,
  asset, paid API/infrastructure, AI, billing or production deployment. Existing
  843-record license inventory and last-known 17 npm advisories remain unresolved;
  no fresh vulnerability scan or legal clearance claimed. Remote CI unobserved.
- Owner-reported retention acceptance after merge (`a552111`): 187 Windows tests
  passed (662.20 s), HTTP smoke passed (10.03 s); local preview scanned 51 entries,
  protected 28, zero candidates, complete. S3 preview scanned/protected two,
  zero candidates, complete. No owner retention apply was performed. Evidence:
  `.data\smoke-ae5bddb56cb64c2c944bc2962d79c6d8`. These are user-supplied results.
- Upgrade requires stopping API/worker, backing up DB/media, and migration 0012.
  No dependency install is required solely for this increment. Restart all
  services; test account deletion only with a disposable account. Runbook and
  recovery/erasure limits: [ACCOUNT_DELETION.md](docs/ACCOUNT_DELETION.md).
- Remaining Phase 2 gates include verified recovery/email delivery, refresh,
  stronger queue/isolation/load/soak controls, allocation-aware online collection,
  formal backup/version erasure, monitoring and production security/legal review.

- Delivery: implementation `49b1cb8` pushed to
  `dev/phase-2-account-deletion`. Automatic PR creation returned GitHub GraphQL
  `Forbidden`; no PR, merge or deployment was performed. Owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-account-deletion

## Phase 2 increment — bounded maintenance and offline orphan preview

- Worker expiration now selects a bounded batch (default 100, allowed 1–1000),
  locks the owner and rechecks status/deadline, instead of expiring an unbounded
  set. Existing terminal staging/deleted-project cleanup and budget release remain
  automatic between renders; active/valid paused uploads stay protected.
- New operator `python -m app.retention` defaults to a nondeleting local/S3 preview.
  Offline apply requires the reviewed digest from a fresh complete inventory and
  an explicit assertion that all writers are stopped. This is intentionally not
  unattended online orphan deletion: an uncommitted upload can have no DB row.
  No valid saved-project age expiry is introduced.
- Recognizes only canonical UUID layouts for known owners; removes aged untracked
  media/upload trees or unreferenced noncurrent failed/lost/cancelled attempt
  artifacts in terminal projects. All known jobs/sessions, current/winning attempts,
  source/output/part references (including cross-project references), young/unknown
  data, symlinks/junctions/hardlinks/special files remain protected. Minimum grace
  24 hours; local modification/change times and S3 LastModified must qualify.
- Bounded scans (default 10,000 entries, maximum 50,000; 100 S3 pages per prefix),
  namespace/DB/root-bound digest, changed/incomplete/nonprogressing inventory refusal,
  repeated metadata/reference checks and exact-key S3 deletion. Private nonversioned
  stores only. Group failure is reported without raw provider messages. Offline
  assertion is not distributed-writer detection; backup/restore reconciliation and
  no concurrent filesystem/provider writers remain essential safety requirements.
- No migration, new configuration default, dependency, mobile source or native
  change. No paid infrastructure/API, AI, billing or reference-kit assets added.
  Existing 843-record inventory and unresolved license/security/17 last-known npm
  advisory gates remain; no fresh vulnerability scan or legal clearance claimed.
- Baseline **168 backend tests passed (30.69 s)**. Final **187 tests passed on
  SQLite (34.59 s) and PostgreSQL (41.30 s)**, no skips; one existing Starlette/httpx
  warning each. Adds preview-only behavior, digest/offline/grace/scan protections,
  every known job state, new data/committed intents, unsafe links/files, cross-project
  references, stale-winner/source preservation, namespaces, S3 failures/versioning/
  pagination and bounded expiry/reservation checks. TypeScript and all **30 client
  tests** passed. No new native/device/build claim; app code was unchanged.
- Real local/API restart/resume/render/download/deletion smoke passed (baseline
  1.74 s; 1080×1920/30 fps/4.9 s). After stopping only its own writers, actual CLI
  preview/offline refusal/empty apply and synthetic old-orphan apply passed while
  a known source survived. Ignored synthetic evidence:
  `.data/smoke-c5fd8fa9cf75441086dd6a0bbd158a48/`.
- Real disposable S3 direct-upload/restart/checksum/expiry/sealing/render/download/
  project cleanup regression passed, followed by offline exact-object orphan
  removal and known-source preservation. CLI guards also passed. Baseline 7.88 s
  includes the six-second signed-download expiry wait, not total stress transfer
  or container startup. Output 1080×1920/30 fps/4.9 s. Evidence:
  `.data/nextphase-s3-smoke-6f61f15eee78/workflow/`. Retention fixture advances a test
  clock two days; it does not claim to have observed a real 24-hour waiting period.
- Doctor, pip and diff checks passed. CI now triggers for the retention fixture;
  remote CI remains unobserved. No production deployment or actual owner's media
  cleanup was performed. Apply testing used only isolated synthetic storage.
- Owner-reported merged direct-upload acceptance (`2ee5e27`): Windows migration
  0011, **168 backend tests (375.16 s)**, TypeScript and 30 client tests passed;
  local smoke passed (63.83 s; `.data/smoke-0d7a76b8e9bc4c6ba0bd984fd98d49d1`).
  Those slower timings were reported, not diagnosed as a specific hardware issue.
  Pixel normal-flow checks passed. Owner then configured local SeaweedFS/USB 8333
  and reported direct resume/render/save, pause over 60 s followed by resume/save,
  and discard preserving the original all worked. This is owner-reported device
  acceptance, not independent evidence of a specific HTTP expiry response or
  physical removal of that owner's server objects. The earlier unquoted PowerShell
  IP truncation was resolved using quoted argument arrays.
- Upgrade/runbook and exact remaining limits: [retention](docs/RETENTION.md).
  No apply is required just to upgrade; start with preview, and stop/back up all
  writers before any reviewed removal. Remaining: online allocation-aware orphan
  GC, global capacity/cost and load/soak controls, formal retention policy, full
  account/version/backup erasure and the rest of Phase 2 security/auth/queue work.

- Delivery: implementation `658f967` pushed to `dev/phase-2-retention-cleanup`.
  Automatic PR creation returned GitHub GraphQL `Forbidden`; no PR/merge/deployment
  was performed. Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-retention-cleanup

## Phase 2 increment — signed direct chunks and verified sealing

- `DIRECT_UPLOADS_ENABLED=false` by default. Updated mobile can negotiate direct
  chunks only for new capable sessions when enabled with private S3. Existing
  upload keys, modes, checksums, offsets, rights and normal PC API uploads survive.
  No paid API/infrastructure, cloud deployment, AI or billing was activated.
- Migration **0011_direct_uploads** preserves legacy sessions/parts as API uploads;
  adds namespace/transfer/cleanup fields, remote part references and one durable
  random grant per offset. Renewal reuses the bounded incoming key and refuses
  changed content intent. No dependency was added; existing 843-record inventory,
  license notices and last known 17 npm findings remain applicable, not cleared.
- Owner-only part-url signs exact temporary PUT key/length/checksum/type for at
  most 60 s. Part commit downloads and rehashes the chunk, checks exact length and
  stores a separate private sealed reference before acknowledging. Signed links
  cannot write sealed chunks, source originals or results. Lost replies/restarts
  recover from DB offsets; concurrent commits publish once; abort/expiry/deletion
  during sealing cannot publish. Source completion verifies the sealed manifest
  and whole source before media admission and one-job publication.
- Mobile uses raw storage PUT with no bearer/cookies/redirects, validates the
  target/required headers and retains its journal/copy on expired-link/network
  failure. API 401 handling remains separate; original footage is never removed.
  No new native permission/module. Transfers are foreground only; no encoding/AI
  was moved onto phones. Owner subsequently reported S3 direct Pixel acceptance (see retention follow-up above).
- Direct admission reserves three source copies plus two render caps; reservation
  transfers once to the job and remains conservative until project deletion.
  Terminal staging removal waits for recorded signed expiry, retries failures and
  rescans late writes. Project deletion releases only after project and staging
  cleanup. Capabilities cannot be recalled by logout/abort alone; retained grant/
  operational tombstones, long in-flight writes, orphans, backup/account erasure,
  physical/global quotas and ingress/cost/ACL/provider policies remain limits.
- Baseline before changes: **158 tests passed** (29.08 s). Final **168 backend tests
  passed on SQLite (30.00 s) and PostgreSQL (37.23 s)**, no skips; one existing
  Starlette/httpx warning each. Coverage adds ownership, capability opt-in, legacy
  digest/migration compatibility, corruption/length rejection, renewal bounds,
  concurrent commits, mutation after sealing, abort races, namespaces and cleanup.
  Final direct PostgreSQL race tests also passed separately (9 tests, 2.76 s).
- An initial PostgreSQL run hit stale synthetic tombstones from a reused test DB,
  affecting an existing cleanup-priority assertion. The tests now create/drop a
  per-run schema inside the explicitly selected *_test DB, preserving unrelated
  data; backend tests also force local/off storage defaults to avoid a developer's
  real provider configuration. The full suite passed with this isolation. Migration
  preservation is still exercised independently in dedicated test schemas.
- TypeScript, **15 upload + 8 auth/API + 7 export tests** and Android Hermes export
  passed (1,011 modules / 2.69 MB). Includes sealed-ack restart without retransmit,
  lost direct PUT reply recovery, expired capability preserving intent, forbidden
  insecure origin and no API credentials in storage requests. Native/network
  adapters are mocked; this is not a physical direct upload or APK validation.
- Real disposable local S3 smoke passed a partially disconnected PUT, API kill/
  restart, resumed 51 MiB source at byte 1,048,576, true expired-link rejection,
  same-key renewal, sealed-path/signed-length tamper denial, overwrite protection,
  checksum/rights preservation, one-job completion and actual render/download/decode.
  Physical upload/project prefix removal, local cleanup and zero owner reservation
  were checked. Output 1080×1920/30 fps/4.9 s. Final baseline flow 8.30 s includes
  the six-second signed-GET expiry wait; it excludes stress-source generation and
  direct transfer setup and is not a production speed/SLA claim. Ignored evidence:
  `.data/nextphase-s3-smoke-17243d3c0827/workflow/`.
- Backed up the isolated PostgreSQL application DB, rebuilt and applied migration
  0011; API/worker/S3/DB healthy. Integrated external HTTP direct resume/signature/
  render/download/deletion smoke passed (8.77 s baseline including expiry wait;
  external API not restarted). Operator read-back verified removed direct staging,
  project objects and manifest, retained grant tombstones and released budget.
- Normal local/API restart/resume/render/download/deletion smoke also passed on
  migration 0011: 1.91 s baseline, 1080×1920/30 fps/4.9 s, owner isolation and
  physical cleanup/budget release. Ignored synthetic evidence:
  `.data/smoke-45b7556abb534c4daf0f28d7936d172d/`. Doctor, pip and diff checks passed.
- Owner-reported prior merged object-storage/CI-fix acceptance (`1734c1c`): Windows
  dependencies/migration succeeded, **158 tests (109.20 s)** and full local smoke
  passed (2.20 s; `.data/smoke-572d1192c2534f0abf4374f5e0a0e67b`). Owner subsequently
  reported old/new Pixel upload/render/save/delete checks worked. S3 was explicitly
  off on that PC; these are owner reports of the prior local path, not direct QA.
- Upgrade and acceptance: [direct uploads](docs/DIRECT_UPLOADS.md). Stop services,
  back up DB/media, pull, migrate 0011 and update API/mobile together. No new pip/npm
  installation is required solely for this increment. Keep normal PC local/off;
  run the disposable Docker S3 smoke separately. Review/remote CI and physical
  direct Pixel/OS tests remain; no independent CI success or merge is claimed.
- Remaining Phase 2: production IAM/TLS/edge abuse/cost controls, fully stateless
  validation, broad provider compatibility, retention/orphan/version/account/backup
  erasure, verified auth delivery/recovery, robust broker/isolation, observability
  and representative load/soak. Later AI styles and payments stay disabled.

- Delivery: implementation `3311468` pushed to `dev/phase-2-direct-uploads`.
  GitHub GraphQL PR creation returned `Forbidden`; no PR was created or merged.
  Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-direct-uploads

## CI follow-up — private S3 startup permissions

- Owner supplied a failing GitHub SQLite job: the pinned image pulled successfully,
  then the S3 readiness check exhausted retries. The supplied output did not include
  its server log; remote CI success is not claimed here.
- Found and reproduced a runner-dependent permission defect: the pinned image's
  entrypoint drops to seaweed UID 1000, but host-created 0600 config can belong to
  UID 1001 on GitHub. Verified UID-1001-owned 0600 data is unreadable to seaweed;
  copying into the private data directory and setting seaweed ownership restores
  access while retaining mode 0600. No broad secret permissions or privileged
  server workaround were introduced.
- Smoke startup now creates the container, copies its generated config into /data
  before start, and lets the official entrypoint assign data ownership. No host
  secret bind mount remains. Readiness reports only a safe error type/service code
  and detects early container exit. Failure prints redacted log tail; CI retains
  only sanitized server.log for three days, excluding credentials and workflow data.
- **158 backend tests passed on SQLite (31.68 s)**, including two new diagnostics
  privacy regressions (credentials, signed URL parameters, response-less connection
  errors and unsafe service messages). One existing Starlette/httpx warning.
  Full real S3 restart/resume/render/download/signature/expiry/physical-delete smoke
  passed with the corrected startup, 1080×1920/30 fps/4.9 s output; baseline 8.76 s
  includes the six-second signature expiry wait. Synthetic ignored evidence:
  `.data/nextphase-s3-smoke-f2a5bc37de52/workflow/`.
- No API/mobile/schema/dependency change. Prior PostgreSQL validation remains as
  recorded below; not rerun for this script/workflow-only correction. GitHub rerun
  must establish remote acceptance after this branch update. No paid services.

## Phase 2 increment — private S3 originals/results and signed downloads

- Optional `MEDIA_BACKEND=s3` stores validated originals and fenced rendered MP4s
  in an existing private S3-compatible bucket. Local remains default; no cloud
  account/bucket, paid API/infrastructure, AI, billing or subscription was activated.
  This is the first object-storage increment, not all Phase 2 work completed.
- Migration **0010_object_backend** retains existing jobs as local and adds a
  nullable namespace fingerprint for new remote jobs. Existing accounts, paths,
  rights records and pending upload offsets remain intact. A changed internal
  endpoint/bucket blocks reads/rendering/deletion rather than claiming empty
  replacement storage was erased. No automatic old-media migration is supplied.
- UUID-only keys, bounded SHA-256 uploads and full source download verification;
  FFmpeg receives local attempt scratch, never an S3/HTTP input URL. Validated
  output must be stored before DB claim-fenced success. API-mediated resumable
  ingestion remains; direct signed uploads and remote part staging are pending.
- Owner-authenticated streaming downloads preserve the mobile Save/Share contract
  and keep bearer credentials on the API origin. New owner-only POST download-link
  issues exact-key SigV4 GET capabilities for 5–60 s. Anonymous, other-owner and
  deleted-project API access are refused. Already-issued URLs remain valid until
  expiry or object removal, even after logout/tombstoning; downloaded/in-flight
  copies cannot be recalled. Signed URLs must not enter logs/analytics/public git.
- Deletion retries remove only the canonical remote project prefix and private
  staging/scratch. Partial/unavailable deletion or namespace mismatch retains the
  reservation and unset media_deleted_at. Versioned/suspended buckets are refused;
  version-aware erasure/retention is not implemented. Local inventory cannot infer
  unknown retained remote usage from an empty scratch directory.
- SDK: boto3 1.43.126 with seven total new installed Python records including its
  transitives. Inventory regenerated to **843** records; packaged LICENSE/NOTICE
  files preserved under docs/licenses/s3-sdk/. Local test server SeaweedFS 4.06 is
  digest-pinned; official Apache-2.0 notice preserved. This is metadata/notice review,
  not full OS/container/transitive, legal/patent or production clearance. No kit
  code/assets were copied. Mobile dependency graph unchanged; last known 17 npm
  findings remain unresolved, not freshly audited by this increment.
- Final backend checks: **156 tests on SQLite (28.04 s) and PostgreSQL (37.16 s)**,
  no skips; one existing Starlette/httpx warning each. Includes legacy/additive
  migration, remote fault/ownership/hash/byte bounds, cancellation during output
  publication, namespace-safe deletion, versioning refusal and unknown-usage guards.
  Mobile TypeScript and all **26 client tests** passed; mobile source/dependencies
  did not change, so no new native-device or APK/export claim. Doctor, pip check
  and whitespace checks passed. Remote CI was configured, not independently observed.
- Final disposable real S3 HTTP smoke passed API kill/restart, auth/revocation,
  interrupted 51 MiB upload/resume, acknowledgement/checksum/repeat-safe completion,
  stored originals, remote render publication, API download/full decode, signed GET,
  anonymous denial, forbidden PUT, signature tamper and actual five-second expiry.
  Deletion read-back confirmed the remote prefix empty plus scratch removal and
  reservation release. 1080×1920/30 fps/4.9 s output; workflow 7.90 s **including a
  six-second expiry wait**, not a performance benchmark. Ignored synthetic evidence:
  `.data/nextphase-s3-smoke-a8cb786b75fa/workflow/`.
- Default local-storage restart/resume/render/download/deletion smoke also passed
  on the finalized migration (baseline 1.71 s; 1080×1920/30 fps/4.9 s output),
  including physical cleanup and budget release. Ignored synthetic evidence:
  `.data/smoke-beae1d2063bc42ddadf072081b9137d0/`.
- Rebuilt the isolated PostgreSQL/SeaweedFS/API/worker stack after DB backup and
  applied finalized migration 0010. All services healthy; real integrated HTTP
  auth/resume/signed-link/render/download/deletion smoke passed (8.68 s including
  expiry wait; external API not restarted). Operator read-back verified both remote
  synthetic jobs' namespace, original/output objects, removed scratch, physical
  deletion, reservation release and preserved old local job metadata. No paid cloud.
- A validation run initially exhausted local Docker disk because the test server
  preallocated large volumes; no success was claimed for that failed run/build.
  Removed only the agent-created disposable server, bounded test volumes to 64 MiB
  (16 slots), added writable-object readiness and owned anonymous-volume cleanup,
  then reran successfully. Existing application volumes were preserved. The draft
  migration was finalized on disposable databases before publication; the validation
  application DB was restored from its pre-increment backup before the final upgrade.
- Owner-reported acceptance of the merged acknowledgement increment (`718ba14`):
  Windows migration passed, **142 tests (54.80 s)**, TypeScript and all **26 client
  tests** passed; restart/resume/acknowledgement/render/download/cleanup smoke passed
  (baseline 5.09 s; evidence `.data/smoke-3c2929a56ae042269b2d2cc0617426f8`). Owner
  subsequently reported all listed Pixel acknowledgement/reset/resume/discard and
  render/save checks worked. These are owner reports, not independent device runs.
- Upgrade commands, exact storage/signed-link/deletion boundaries and local Docker
  smoke: [private object storage](docs/PRIVATE_OBJECT_STORAGE.md). Stop services,
  back up DB/media, install updated Python requirements, migrate 0010, restart and
  recheck old/new projects. Keep the PC on default local mode unless S3 is explicitly
  configured. No mobile npm/native dependency or automatic production rollout.
- Remaining: direct signed uploads with immutable-part protection, fully remote
  staging/stateless workers, orphan reconciliation and full account/version/backup
  erasure; IAM/secret-manager policies, TLS/edge limits, production queue/isolation,
  representative load/soak and legal/provider review. No production cloud, broad
  compatibility/performance/SLA or full privacy compliance is claimed.

- Delivery: implementation `85dabde` pushed to `dev/phase-2-private-objects`.
  Automatic PR creation returned `Post https://api.github.com/graphql: Forbidden`;
  no PR was created, merged or deployed. Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-private-objects

## Phase 2 increment — upload acknowledgement and bounded media profile

- Create Short now requires an explicit, initially unchecked rights and server-
  processing acknowledgement. Choosing another file resets it. Both upload APIs
  enforce `upload-rights-v1`; strict session JSON rejects false/string/numeric
  booleans. This records authenticated self-attestation, not verified ownership,
  legal clearance, consent from depicted people or permission for AI training.
- Additive migration **0009** records nullable version/server UTC receipt time on
  sessions and jobs. Historical records remain unknown; no fabricated backfill.
  Old paused intents require explicit reconfirmation while retaining their key,
  private copy and acknowledged offset. Replay preserves current receipt times.
- Discard works without asserting rights. Owner-key locking and a zero-byte,
  zero-budget aborted tombstone prevent a late creation from resurrecting an
  intent discarded before its session ID was saved. Stale screens cannot replace
  a newer pending intent. Network failure retains the private saved copy.
- FFprobe and FFmpeg now restrict demuxers, decoders and protocols to the documented
  baseline profile and file-only input. Validate actual container, one video,
  optional single audio track, pixel/rate/audio/stream limits; worker revalidates
  queued sources before rendering. Selected allocation/probe/thread limits apply.
  This is not antivirus, a filesystem sandbox or a total memory/disk quota.
  Real H.264/MP4, HEVC/MOV, VP9/WebM and AV1 render tests pass; a disguised remote
  playlist cannot contact the HTTP canary through probe or renderer. HDR/VFR and
  broad real-device codec/hostile-file coverage remain unverified.
- **142 backend tests passed on SQLite (27.76 s) and PostgreSQL (45.00 s)**,
  no skips, one existing Starlette/httpx deprecation warning each. Includes strict
  acknowledgements, preserved legacy migration data/progress, repeated completion,
  concurrent create/discard, owner isolation, media profile and prior regressions.
- TypeScript, **11 upload + 8 auth/API + 7 export logic tests** passed. Android
  Hermes export passed (1,011 modules / 2.69 MB). Native adapters are mocked in
  client tests; owner subsequently reported the Pixel checkbox/reconfirmation flow passed (see above).
  Pip dependency and diff checks passed. No dependency changes: inventory remains
  836 records; last audit remains 17 unresolved (4 high, 12 moderate, 1 low),
  not a fresh vulnerability scan or commercial dependency clearance.
- Real isolated HTTP smoke passed restart/auth/revocation, interrupted 51 MiB
  upload, checksum/offset and acknowledgement preservation, repeat-safe completion,
  queue/render/download/decode, deletion cleanup and reservation release. Output
  1080×1920, 30 fps, 4.9 s; baseline workflow 1.99 s. Synthetic ignored evidence:
  `.data/smoke-0fd5ca6c05584616bcd2fcfbe05c9dfc/`.
- Backed up the isolated PostgreSQL application DB; rebuilt local Compose images,
  applied migration 0009 and verified healthy API/worker/database. External HTTP
  smoke passed auth/resume/acknowledgement/render/download/deletion access controls
  against those services (2.66 s baseline). This external run did not restart the
  API or independently inspect container filesystem cleanup. No paid cloud deployed.
- Owner-reported acceptance of the previously merged Save/Share/storage increment:
  Windows 106 backend tests, complete smoke (3.95 s), TypeScript and 22 client
  tests passed; inventory found 23 records, zero unverified trees, no deletion.
  Owner reported all Pixel checks worked, including separate Save/Share. This is
  normal-flow acceptance; native denied-permission/OS-full errors remain untested.
- Upgrade: stop API/worker/Expo, back up DB/media, pull this increment, run migration
  0009 and restart updated API/mobile together. No additional inventory or package
  installation is required solely for this increment. Old upload clients receive
  422/409 until updated. Commands and device checklist:
  [upload consent and media guide](docs/UPLOAD_CONSENT_AND_MEDIA.md).
- Phase 2 remains open: broader device/error QA, security and
  licensing review, private object storage/production queue/deployment foundations,
  retention and capacity controls. AI styles, transcription, provider calls,
  subscriptions and paid infrastructure are not enabled. Next implementation scope
  must follow the roadmap and the owner's approval boundary for paid services.

- Delivery: implementation commit `8eb9db3` pushed on
  `dev/phase-2-consent-media`. Automatic PR creation returned GitHub GraphQL
  `Forbidden`; branch push succeeded. Review PR must be opened manually:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-consent-media

## Phase 2 increment — native Save/Share and storage admission budgets

- Replaced the combined cache-download/share button with separate Save video to
  phone and Share video actions. Save resolves the native media-library write
  before confirming success; it never opens Share. Share never saves automatically.
  Denied permission, missing/empty downloads, 401/404/network and native save errors
  do not claim success or fall back to another action. Per-screen export guard
  prevents overlapping export actions; all editing remains server-side.
- Added SDK-matched Expo Media Library 18.2.1 (declared MIT), verified its official
  SDK 54 upstream license and preserved the notice in docs/licenses/. Inventory
  regenerated to 836 records. The npm package omits a standalone license file;
  inventory points to the preserved upstream notice. Full legal/OS/transitive
  clearance remains open. Fresh npm audit is unchanged: 17 unresolved (4 high,
  12 moderate, 1 low). No paid service, billing or proprietary kit assets added.
- Save uses add/write permission where needed; Android API 33+ can add the app's
  own video without broad read permission. Native config introspection verified
  broad Android media read/location permissions blocked and iOS add-only text
  present, with no photo-library read description. Expo Go's full-access warning
  is not a claim that this app reads the gallery. Owner subsequently reported normal Pixel Save/Share working (see above).
- Migration 0008 adds nullable job/session byte budgets and per-attempt render caps.
  New admissions reserve declared/received source bytes plus two bounded render
  attempts (default 64 MiB each) against a per-account 5 GiB budget. Owner-row
  transactions prevent concurrent accepted uploads overbooking; completion swaps
  one session reservation for one job. Replay/accepted sessions remain repeat-safe
  at capacity or after a config reduction; stored caps/reservations are retained.
- New owner-only GET /api/v1/me/storage powers Account's used/reserved storage card.
  New uploads return clear 409 errors for full or unverified inventory. Failed,
  cancelled and completed jobs retain reservations until deletion media cleanup;
  aborted/expired staging retains its reservation until cleaned. These are local
  resource admission budgets, not paid credits or strict physical filesystem quotas.
- Offline `python -m app.storage --reconcile` inventories existing canonical media
  trees while API/workers are stopped. Missing/unsafe/permission-denied trees stay
  unknown and block only that owner's new uploads rather than being guessed as zero.
  Existing accounts/sessions/media are preserved; no media is deleted by inventory.
  Migration alone does not fabricate old usage; this is a required upgrade step.
- FFmpeg output is monitored and validated against its stored cap. Exceeding it
  kills the child, removes its partial artifact and fails with OUTPUT_LIMIT_EXCEEDED;
  it never silently truncates an export. Transient overshoot/temp/spooling/orphan
  files and backups still need physical/global capacity controls and retention.
- **106 backend tests passed on SQLite (25.62 s) and PostgreSQL (37.03 s)**, no skips
  in this Linux environment; one existing Starlette/httpx warning each. Covers
  legacy/resumable admission, exact replay, transfer, config reduction, cleanup
  release, unknown/offline inventory failures, four concurrent HTTP uploads,
  additive migration preservation, real oversize output failure and all prior
  deletion/auth/queue/media regressions. No multi-GiB upload/load-soak claim.
- Clean npm ci, TypeScript, **7 upload + 8 auth/API + 7 export logic tests** and
  Android Hermes export passed (1,010 modules / 2.68 MB). Offline installed-SDK
  compatibility check reports up to date; online Expo Doctor not run. Pip check,
  native config introspection and diff checks passed. Native adapters are mocked
  in client tests; Pixel save/gallery and permission/OS-storage failure tests remain.
- Real isolated HTTP smoke passed API kill/restart, auth limits/revocation,
  interrupted 51 MiB upload/resume, unchanged storage reservation after completion,
  valid 1080×1920/30fps/4.9s render/download/decode, deletion and physical cleanup
  with owner reservation released to zero. Baseline workflow 1.64 s. Ignored
  synthetic evidence: `.data/smoke-cf55070041db417fbbb78c5d9961e1ab/`.
- The isolated PostgreSQL application DB/media were backed up; migration 0008
  and offline inventory succeeded (22 records, zero unverified trees), without
  deleting media. Rebuilt Compose services passed real HTTP auth/resume/reservation
  transfer/render/download/deletion smoke (baseline 2.58 s); the external API was
  not restarted by that run.
- Review delivery: implementation `303c35c` pushed to `dev/phase-2-save-storage`.
  Automatic PR creation returned `Post https://api.github.com/graphql: Forbidden`.
  Manual review link: https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-save-storage .
  No merge/deployment was performed; remote CI not independently observed.
- See [upgrade/inventory, scope and physical acceptance](docs/SAVE_AND_STORAGE.md).
  New `npm ci` is required; custom native builds must be rebuilt for permissions.
  The OS-saved copy remains outside server deletion. No gallery save on a real
  phone, iOS device run, full privacy erasure or production disk ceiling is claimed.

## Phase 2 increment — project deletion and private-volume cleanup

- Migration `0007_project_deletion` adds nullable deletion/cleanup timestamps and an
  index. Existing accounts, sessions, jobs, attempt records and paused uploads are
  preserved; migration itself deletes no footage. No new sign-in is required.
- Owner-only DELETE `/api/v1/jobs/{id}` commits a permanent tombstone before 202.
  All prior statuses can be deleted; repeated owner requests stay repeat-safe and
  other owners receive 404. Lists/detail/download/cancel hide deleted projects.
  Claims are revoked and title/path/linked upload display metadata are scrubbed.
- Owner/job-row locks follow the worker's job→attempt lock order. Active attempts
  are cancelled, stale completion cannot publish, and legacy/session key replays
  return 410 rather than resurrecting the project. Downloads now use private/no-store.
- Worker maintenance and `python -m app.deletion` scan bounded batches of canonical
  private UUID project/staging paths. Stored source/output paths are never deletion
  targets; symlink/junction parents are refused. Failed I/O retries without logging
  customer paths; pending removal precedes successful rescans, with oldest-attempt
  ordering inside each group. Previously cleaned tombstones are rescanned for late
  artifacts. Processing cleanup waits past the original lease plus 30 seconds.
- Mobile adds explicit destructive confirmation, waits for the server's deleted
  acknowledgement and returns to My Shorts. Offline failure stays retryable. It
  attempts removal of the current app download cache and discloses local failure;
  gallery/shared/other-device copies remain. Missing project routes have a back
  action. Confirmed discard of a remotely deleted upload clears only its private
  pending copy after 404/410; network failure does not authorize local deletion.
  Library requests are invalidated on blur so a delayed old list cannot reinsert
  a deleted item after returning from project detail.
- **96 backend tests passed on SQLite (22.53 s) and PostgreSQL (31.89 s)**, no
  skips on this Linux environment; one existing Starlette/httpx warning each.
  Covers all prior media/auth/queue/upload regressions plus deletion ownership,
  all statuses, concurrent completion, a forced lock-order race, actual running
  FFmpeg termination, replay denial, retry/rescan/priority, symlink/path isolation
  and fresh/repeat/additive migration preservation. On Windows the symlink-only
  test skips if the OS lacks symlink creation privileges; other deletion tests run.
- Mobile TypeScript, **7 upload + 8 auth/API client logic tests** and Android export
  passed (1,007 modules, 2.66 MB Hermes). Doctor, pip check and diff whitespace checks
  passed. No dependency changed; the last known 17 advisories (4 high, 12 moderate,
  1 low) and 835-record inventory remain applicable, not cleared by this increment.
- Final isolated real HTTP smoke killed/restarted its API, preserved auth controls,
  resumed a partial 51 MiB upload, verified checksum/one-job completion, rendered,
  downloaded/decoded valid 1080×1920/30fps/4.9 s MP4, then deleted the synthetic
  project. Other-owner delete was denied; future downloads returned 404, key replay
  410, and CLI cleanup physically removed its source/output tree. Baseline workflow
  took 1.66 s. Ignored synthetic evidence:
  `.data/smoke-16124dc67f7649359103bc3f0d6b7d8e/`.
- The isolated Compose/PostgreSQL DB was backed up, migrated and rebuilt. Final
  real HTTP auth/resume/render/download/deletion smoke passed (baseline 2.45 s),
  followed by cleanup CLI and filesystem/DB read-back confirming both synthetic
  deleted project trees absent. That external API was not restarted by the smoke.
- Review delivery: implementation `2c2160a` pushed to `dev/phase-2-project-deletion`.
  Automatic PR creation returned `Post https://api.github.com/graphql: Forbidden`.
  Manual review link: https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-project-deletion .
  The owner subsequently merged the deletion increment into main (`c848d7c`).
  No cloud deployment was performed; remote CI not independently observed.
- Owner-reported Windows validation: 96 tests passed (43.71 s), full restart/render/
  deletion/physical-cleanup smoke passed (baseline 3.83 s), TypeScript and all 15
  prior client tests passed. The owner reported the listed Pixel deletion checks
  worked, while the old Download or share action opened Share instead of saving to
  the gallery. That was the prior cache/share behavior; the Save action above is
  new and still needs device acceptance. These are user-reported results, not cloud
  native-device tests; not every cache/OS/offline edge case was independently captured.
- Scope is known committed project/staging media, not full account/personal-data
  erasure: ID/key/fingerprint/operational tombstones and attempt metrics remain.
  Backup expiry/restore reconciliation, uncommitted orphan GC, object-store erasure,
  legal deadlines and full retention policy remain open. No paid service, AI calls,
  billing, proprietary reference-kit code or new dependency was introduced.
  See [upgrade, cleanup delay and acceptance](docs/PROJECT_DELETION.md).

## Phase 2 increment — render timing records and operator report

- Migration `0006_render_attempts` adds one durable record per newly claimed render
  attempt, transactionally with the claim. Existing users, auth sessions, completed
  paths and upload state remain intact; historical measurements are not backfilled.
- Fenced completion saves monotonic observed render wall time and successful output
  size. Cancellation records the attempt even if the worker never returns; observed
  cancellation time can be filled afterward. Lease recovery leaves crashed work
  unmeasured rather than guessing compute. Retry metrics cannot overwrite a winner.
- Added private operator CLI `python -m app.telemetry`: nearest-rank P50/P95 and
  sample counts for observed attempts, first-claim queue wait and successful job
  turnaround; states/retries/output bytes plus unknown and truncated coverage.
  Reports omit emails, tokens, IDs, paths and titles. Unexpected worker errors
  no longer log raw exception text/customer paths.
- Optional decimal hourly-rate calculation covers observed wall time only. Default
  cost stays null. It is neither CPU seconds, VM billing, full variable cost nor
  a provider charge. No provider call, provisioning or billing was introduced.
- **81 backend tests passed on SQLite (18.61 s) and PostgreSQL (22.39 s)**, no skips,
  one existing Starlette/httpx deprecation warning each. Includes unique attempt
  creation under four concurrent claimant processes, failures, cancellation, crash
  recovery, stale completion, report privacy/coverage/percentiles/rates and additive
  migration preservation. All prior media/auth/upload/queue regressions passed.
- Real HTTP smoke passed cancellation, persisted auth limits/revocation across API
  kill/restart, partial interrupted 51 MiB upload/resume, repeat-safe completion,
  render/download/whole MP4 decode and owner isolation. Baseline output was
  1080×1920, 30fps, 4.9 s; baseline workflow 1.89 s. Its aggregate report verified
  two measured successful attempts and 17,308,533 total accepted output bytes.
  Synthetic evidence (ignored): `.data/smoke-ed3af74c646c49ddbaa3496cace98a36/`.
  This tiny synthetic sample is not a production performance/cost baseline or SLA.
- Backed up and migrated the isolated Compose/PostgreSQL application DB; rebuilt
  services passed real auth/resume/render/download smoke (baseline 2.28 s). The
  external API was not restarted by that run. Its operator report confirmed two
  measured successful attempts and clearly identified 10 older/unclaimed jobs
  without attempt records. Calculation-only hourly-rate input also passed.
- Doctor, mobile TypeScript, all 6 upload + 7 auth client tests and pip check passed.
  No mobile source/dependency changed in this increment; no new native feature or
  Android bundle test is claimed. Existing 17 dependency advisories and 835-record
  inventory remain applicable and unresolved; commercial clearance still pending.
- Review delivery: implementation commit `9a500dd` pushed to
  `dev/phase-2-render-telemetry`. Automatic PR creation again returned
  `Post https://api.github.com/graphql: Forbidden`. Create the review PR at
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-render-telemetry .
  The owner subsequently merged this telemetry increment into main (`0648ed2`);
  no cloud deployment was performed. Remote CI was not independently observed.
- Owner-reported Windows/Pixel validation passed after merge: 81 backend tests
  (76.12 s), restart/resume/auth/render/telemetry smoke (baseline 2.24 s), and a new
  Pixel upload/render/download/playback. Its local report contained one successful
  28.766 s measured render, 0.088318 s first-claim wait and 7,206,440 output bytes;
  cost remained null. Thirteen older/unclaimed jobs had no attempt records, as
  expected. This is one sample/user-supplied evidence, not a performance baseline.
- See [migration, definitions and operator checks](docs/RENDER_TELEMETRY.md).
  Full tracing/exporters, CPU/GPU/peak-memory measurement, representative load/soak,
  cost ceilings, retention/deletion, object storage and verified email recovery
  remain Phase 2 work. Paid services, AI processing and billing remain disabled.

## Phase 2 increment — revocable authentication sessions

- Migration `0005_auth_sessions` adds persistent session records and shared auth
  counters. Fresh/repeat upgrades and 0004→0005 preservation of users, completed
  output paths, paused upload offsets and parts are tested on both databases.
- Access tokens require issuer/audience/subject/issued-at/expiry/random session ID
  plus an unexpired, unrevoked DB record. IDs are hashed at rest. Current-session
  logout, logout-all and authenticated password change persist across API restarts.
- Password change verifies the current scrypt password and atomically revokes all
  sessions. Login/password operations serialize on the owner row; a revoked or
  expired session is rechecked after the password-change lock. Existing password
  hashes remain valid. New passwords require 12–128 characters.
- Atomic fixed-window limits default to 5 login attempts/account, 30 login attempts
  per peer, 10 registrations/peer and 5 password attempts/account per 900 seconds.
  Successes count too. HMAC keys avoid plaintext rate-table IP/email storage;
  denied requests return Retry-After. Dummy scrypt hides the unknown-account fast
  path; registration's existing 409 enumeration behavior remains documented.
- Docker/README/API upgrade launchers disable automatic forwarded-header trust.
  Production proxy/TLS/edge configuration remains a separate reviewed boundary.
  Expired sessions/counters are cleaned by worker maintenance between renders.
- Mobile adds Change password, Sign out and Sign out all sessions, saved-session
  validation and authenticated-401 handling (including chunk requests/download).
  Serialized secure-storage writes and originating-token checks prevent delayed
  responses from deleting a newer login. Offline logout retains the credential
  until server revocation succeeds. Pending upload journals remain owner-scoped.
- **68 backend tests passed on SQLite (25.20 s) and PostgreSQL (26.31 s)**, no skips,
  with one existing Starlette/httpx deprecation warning each. Includes concurrent
  counters, JWT claim rejection, revocation scope, expiry, password and race tests,
  plus all previous queue/media/migration/upload regressions.
- Clean npm ci, **6 upload + 7 auth client logic tests**, TypeScript, offline SDK
  compatibility check and Android Hermes export passed (1,007 modules / 2.66 MB).
  These use adapters for native storage/network and are not physical-device tests.
  Pip check passed. No dependency was added; inventory remains 835 records. A fresh
  npm audit still reports **17 unresolved** (4 high, 12 moderate, 1 low).
- Isolated real HTTP smoke: killed/restarted API; revoked token remained rejected,
  valid session stayed valid and exhausted login window still returned 429.
  Password change/all-session logout passed. The same run resumed the approximately
  51 MiB source at byte 1,048,576 after partial disconnect/restart, verified SHA-256,
  completed as one job and rendered/downloaded/decoded valid 1080×1920, 30fps,
  4.9 s MP4; baseline flow took 1.51 s. Evidence (ignored, synthetic only):
  `.data/smoke-9333e84beac64e07a124d4d3af774d39/`.
- Local Compose/PostgreSQL was backed up, migrated, rebuilt and passed auth plus
  partial-disconnect/resume/one-job/render/download HTTP smoke (baseline 2.39 s);
  the externally running API was not restarted by that smoke.
- **Upgrade behavior:** old bearer tokens require one new sign-in; use the existing
  account/password to recover the same projects/pending upload. See
  [Windows upgrade and acceptance steps](docs/AUTH_SESSIONS.md).
- Review delivery: implementation commit `8482277` pushed to
  `dev/phase-2-auth-sessions`. Automatic PR creation is blocked by GitHub API
  access returning `Forbidden`; the owner can create it from
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-auth-sessions .
  The owner subsequently merged this auth increment into main (`c191c53`).
  No cloud deployment was performed.
- **Owner-reported Windows/Pixel acceptance passed 2026-11-07:** 68 backend tests
  (65.40 s), all 13 mobile client tests, TypeScript and restart/resume/render smoke
  (baseline 2.31 s). The owner confirmed the listed Pixel sign-in, current/all-session
  sign-out, password-change and upload/render/download checks all worked. These
  are user-supplied results, not device tests executed by the cloud agent.
- **Remaining gates:** verified email delivery, forgot-password recovery, refresh rotation, notices,
  admin MFA, edge abuse/body limits and production security/retention review.
  No mail credentials are configured, so no unauthenticated recovery bypass or
  simulated email verification is supplied. Phase 2 remains in progress. AI and
  billing stay disabled; no paid service/infrastructure was enabled.

## Phase 2 increment — durable resumable uploads

- Migration `0004_upload_sessions` adds owner/key-unique session records, verified
  part metadata, expiry and cleanup state. Existing jobs/download paths are retained.
- Authenticated create/get/parts/complete/abort routes provide fixed-size sequential
  SHA-256 verified chunks and authoritative DB offsets. Exact part/complete retries
  are repeat-safe; changed bytes, gaps, invalid media and cross-owner access fail.
- Unexpired uploads reserve queue capacity, shared with legacy submissions.
  Completion exchanges an existing reservation for one job, including after a
  configured limit reduction. Abort/expiry releases the slot. Legacy upload still works.
- Parts are fsynced and atomically published before their offsets commit. Completion
  rehashes every part and source, verifies size/FFprobe limits, then persists one job.
  Chunk receive deadlines bound slow requests; aborted/expired/complete staging data
  is cleaned in bounded worker maintenance batches or via `python -m app.upload_cleanup`.
- Mobile now saves a private copy plus a per-account two-slot pending journal,
  reads/hashes one bounded chunk at a time, shows acknowledged-byte progress and
  offers Pause/Resume/Discard. It rechecks server offsets after interruption/restart.
  Transfers are foreground only; app data and the saved file must remain intact.
- **47 backend tests passed on SQLite** (17.57 s) and **47 on PostgreSQL** (19.09 s),
  no skips; one existing Starlette/httpx warning each. Coverage includes concurrent
  create/parts/complete, checksum and ownership failures, request timeouts, lost
  commit acknowledgements, expiry/cleanup, invalid media and shared reservations.
- Real HTTP smoke transferred an approximately 51 MiB synthetic source in 1 MiB
  chunks, disconnected halfway through a part, forcibly killed/restarted its API,
  resumed at the last acknowledged 1,048,576 bytes, completed twice as one job,
  verified whole-source SHA-256, rendered/downloaded and decoded valid MP4 output.
  Live Compose/PostgreSQL also passed interrupted-part resume and completion/render;
  that externally running stack was not restarted by the smoke command.
- Clean npm ci, **6 mobile recovery-logic tests**, TypeScript, offline SDK check,
  Android Hermes bundle (1,004 modules / 2.65 MB) and pip check passed. The six
  client tests use native/network adapters across JS runtime restarts, not a device.
- Added SDK-compatible expo-crypto 15.0.9 (declared MIT) for bounded checksums/UUIDs;
  inventory has 835 records. Audit remains **17 unresolved** (4 high, 12 moderate, 1 low).
- **Owner-reported Windows/Pixel validation passed after merge**: 47 backend tests
  (110.87 s), six upload client tests, TypeScript, real restart/resume smoke
  (baseline 3.91 s), upload/pause/resume, saved-upload recovery, discard and download.
  These device results were supplied by the owner, not executed by the cloud agent.
- Private filesystem/shared volume only: no cloud object store, signed storage URLs,
  OS background transfer guarantees, complete retention policy or production abuse
  controls. All intensive video processing remains server-side; paid APIs and billing
  remain disabled. See `docs/RESUMABLE_UPLOADS.md` for migration/protocol/limitations.

## Prior Phase 2 increment — upload replay, cancellation and queue controls

- Added migration `0003_submission_keys`, retaining prior rows/downloads. Optional
  owner-scoped Idempotency-Key plus server-side source/settings fingerprint prevents
  duplicate accepted jobs on replay; changed requests under a key return 409.
- Added owner-only queued/processing cancellation, terminal cancelled status,
  repeated-cancel safety, lease revocation and cooperative FFmpeg kill/reaping.
  Completed/failed jobs cannot be cancelled. No cancelled output is downloadable.
- Configurable defaults: max three active jobs and one processing job per owner.
  Short owner-row transactions protect admission and claimant capacity checks.
  Replay is checked before queue capacity; full queue returns 429/Retry-After.
- Mobile preserves the current form's submission key across network failures,
  guards double taps, adds a confirmation/cancel action and stops terminal polling.
  Native interaction recheck remains outstanding for these new controls.
- **33 tests passed on SQLite** (18.33 s) and **33 on PostgreSQL** (17.84 s), no skips,
  one existing Starlette/httpx deprecation warning each. Includes simultaneous
  same-key/different-key submissions and same-owner worker races, cleanup/conflicts,
  cross-owner/terminal cancellation, fencing, a real FFmpeg termination test and
  preserving/replaying an accepted upload after a lost commit acknowledgement.
- Live isolated SQLite smoke passed queued cancellation, upload replay, full render,
  owner-only download and decode (4.9 s, 1080x1920/30 fps H.264/AAC, 1.92 s workflow).
  Rebuilt/migrated Compose PostgreSQL passed queued cancellation with worker paused,
  then the replay/render/download smoke with worker restarted (1.88 s workflow).
- Mobile TypeScript and Android Hermes export passed (992 modules / 2.59 MB).
  Remote CI and physical Pixel testing of these new interactions remain unverified.
- At that prior increment there were no new dependencies; the resumable-session
  work above supersedes its upload limitations. Broker, heartbeat, complete abuse
  controls, auth hardening and full retention remain outstanding. No paid services,
  billing or AI processing were activated.
  See `docs/QUEUE_CONTROLS.md` for protocol, limits and migration instructions.
- Owner reports the prior Windows migration passed, all 22 prior tests and the
  migrated smoke passed (2.39 s), and both old/new Pixel downloads worked afterward.
  Those are user-supplied prior-increment results, not tests of this new increment.

## Prior Phase 2 increment — migrations and worker reliability

- Explicit Alembic `0001_baseline` / `0002_job_leases` upgrades. API/worker startup
  checks the version and never creates tables. Checked legacy adoption preserves
  users/completed job paths and rejects unknown schemas. Existing deployments must
  stop services and back up before running the migration; see `docs/PHASE_2_MIGRATIONS.md`.
- Atomic queued → processing compare-and-set claims; PostgreSQL SKIP LOCKED;
  UUID tokens and expiry fence completion and keep each attempt's artifacts separate.
- Expired first attempt requeues; expired second attempt fails with MAX_RETRIES.
  A stale worker cannot publish over a retry or delete the winner's output.
- PostgreSQL required for staging/production. Compose runs a one-shot migration
  before API readiness and worker startup. SQLite remains local development only.
- **22 tests passed on SQLite** (10.61 s) and **22 passed on PostgreSQL** (11.16 s),
  no skips; one existing Starlette/httpx deprecation warning on each run. Tests
  include four claimant processes / 12 jobs, a process crash immediately after
  claiming, stale-token/output rejection, bounded retries, legacy downloads,
  fresh/repeat migration, model/schema equivalence and data preservation.
- Migration-aware live SQLite smoke passed (4.9 s export, 1080x1920/30 fps,
  H.264/AAC, full decode and owner isolation; 1.50 s workflow time). Compose build,
  one-shot migration, repeated startup and PostgreSQL live smoke also passed.
- Mobile TypeScript passed; no mobile source/dependency changes in this increment.
- CI now defines SQLite and PostgreSQL test variants; remote CI remains unobserved.
- **At that increment**, submission idempotency/cancellation were still pending;
  broker, heartbeat, full fairness, billing quotas, storage/resumable uploads, auth hardening,
  full telemetry or retention janitor yet. Claims have bounded leases, not
  exactly-once execution; hard-killed attempts can leave orphan files.

## Implemented and verified

- FastAPI registration/login and signed bearer sessions, scrypt password hashes.
- Per-user job listing/detail/download, UUID storage paths, validated uploads.
- Source cap 600 seconds / 300 MiB; requested output 5–60 seconds.
- Separate polling worker, bounded stale-job retries and terminal render failures.
- Server FFmpeg first-seconds trim/letterbox to 1080x1920, 30 fps, H.264/AAC MP4.
- Six future styles remain explicitly unavailable; no style-dependent effects.
- SQLite native development and Docker API/worker/PostgreSQL startup and live E2E.
- Expo SDK 54 dependencies aligned (React Native 0.81.5; React/React DOM 19.1.0),
  committed npm lockfile, clean `npm ci`, TypeScript and Android Hermes bundle.
- Docker source permissions repaired for unprivileged execution, API HTTP healthcheck
  and worker readiness ordering. Optional build-time CA secret supports the managed
  TLS proxy without disabling verification or putting the CA into image layers.
- Phase 0 ADR, dependency/trust graph, threat model, service contract, work queue,
  metadata inventory and reproducible demo commands in `docs/` and README.
- Mobile preview copy now states baseline processing and avoids promising secure
  transport on the plain-HTTP development API.

## Current validation record

Executed on Python 3.12.14, Node 24.22.1 / npm 11.9.0, FFmpeg 7.1.5.

| Command / check | Actual outcome |
|---|---|
| `python3 scripts/doctor.py` | Python, Node/npm, FFmpeg/ffprobe and Docker found |
| Baseline backend suite before changes | 9 passed |
| `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q` | **14 passed**, 8.44 s; no skips; one Starlette/httpx deprecation warning |
| Added regression coverage | Empty/bad/unsupported uploads, unknown style, blank title, byte-limit cleanup, >600 s source, login/invalid sessions, terminal worker failures, two-attempt stale recovery |
| Actual 60-second render with audio | Passed: 1080x1920, duration >=59 and <=60.00 s; existing >60 request/render rejection tests also passed |
| `.venv/bin/python scripts/smoke_e2e.py` | Real HTTP + isolated SQLite API/worker; queued → processing → succeeded; 1080x1920/30 fps H.264/AAC, 4.9 s; full decode and owner isolation passed; 1.44 s measured workflow time |
| Docker Compose build and `up -d --wait` | Passed after proxy CA trust and source permission fixes; API/DB readiness and separate worker verified |
| Smoke against Docker/PostgreSQL API on port 8002 | Same full workflow passed; queued → processing → succeeded; 4.9 s output, 2.43 s measured workflow time |
| `npm ci --no-audit --no-fund` | Clean lockfile install passed, no forced/legacy peer resolution |
| `npm run typecheck` | Passed |
| `EXPO_OFFLINE=1 npx expo install --check` | Installed SDK metadata reports dependencies up to date; online Expo Doctor not run |
| Android `expo export` | Passed: 989 modules, 2.58 MB Hermes bundle; not an APK/device test |
| `.venv/bin/python -m pip check` | No broken requirements |
| GitHub Actions | Workflow updated for lockfile, Expo check, Android bundle and live smoke; remote CI not yet observed |

Smoke output MP4, reports and logs are kept in ignored `.data/smoke-*`; Android
bundle/assets are in ignored `apps/mobile/.expo/android-export`. Only synthetic
video patterns and a generated sine tone were used. Report timings are single
local runs, source generation excluded, and are not production benchmarks or SLAs.
Byte/source-limit tests exercise the configured handler boundary using a small
limit/mock probe; no 300-MiB fixture or actual >10-minute upload was transferred.

## Follow-up validation after Pixel report

- Clean npm ci, mobile TypeScript and offline SDK compatibility check: passed.
- Android Hermes export: passed, 992 modules / 2.59 MB; does not verify safe-area appearance on hardware.
- Backend regression suite: 14 passed in 10.01 s, one existing Starlette/httpx deprecation warning.
- Live isolated API/worker smoke: queued → processing → succeeded, 1080x1920/30 fps,
  4.9-second H.264/AAC output, full decode and owner isolation passed (1.54 s measured).
- Dependency inventory regenerated for the targeted PostCSS update; current audit
  reports 17 remaining findings. No blanket override, forced resolution or Expo SDK change.
- Owner's Windows results: 14 tests passed in 81.51 s and live smoke passed in 2.69 s,
  followed by successful TypeScript/Android bundle checks and physical Pixel download.
  These are user-supplied results, not remotely executed by this agent.

## Remaining blockers and acceptance limits

- **Android evidence and limits:** owner-reported Pixel test passed using Expo Go
  for SDK 54 on Windows with USB `adb reverse` (ports 8000 and 8081). The supplied
  result screenshot shows documentary, requested 15 s, actual 11.7 s, SUCCEEDED;
  the owner confirmed download worked. Home/style-list screenshots were supplied.
  Exact Pixel model, Android build, media provenance and independent probe of that
  downloaded file were not captured. iOS remains untested. The owner subsequently confirmed the safe-area fix and
  a repeated upload/render/download check all worked on the Pixel.
- **Dependency findings:** current audit reproduced 18 findings (5 high). A targeted
  PostCSS 8.5.32 override reduces this to 17 (4 high, 12 moderate, 1 low), preserving
  Expo SDK 54. Remaining findings are unresolved; see `docs/DEPENDENCY_SECURITY.md`.
- **Commercial license clearance is pending:** `docs/dependency-inventory.json`
  records 835 exact installed/locked dependency records and metadata, not legal
  approval, complete OS/container SBOM or an attribution bundle. Reference ZIPs
  are absent; their original licenses were not independently reinspected. No code
  or assets from them were imported. See `docs/LICENSE_AUDIT.md` and Phase 0 audit.
- **GitHub PR API access:** the actual `gh api` repository request returned
  Forbidden. Existing HTTPS Git read access works. `api.github.com` was added to
  the environment configuration draft; saving the draft does not apply runtime
  access. Review/save the setting and publish as the environment UI requires.
  The development branch `dev/phase-0-1-validation` was committed and pushed successfully.
  `gh pr create --draft` then failed with `Post https://api.github.com/graphql: Forbidden`;
  no PR was created. A review description is prepared in `/tmp/nextphase-pr-body.md`.
  Retry PR creation after API access is applied; Git push access alone is insufficient.
- Python requirements remain version ranges; the inventory records this machine,
  while the mobile lockfile pins npm resolution. No production security
  certification or complete dependency vulnerability review is claimed.

## Not implemented

AI highlights/director integration, ASR/captions, intelligent reframing, motion/3D,
B-roll and six style engines; hardened auth/account lifecycle;
full durable broker, private cloud object storage, OS background transfers,
full account/backup/object-store erasure and retention, production observability; payments, Mobile Money, entitlements,
subscription quotas, legal/store signoffs and commercial production hosting.

## Next steps

1. Review/merge local recovery and observe the new CI run. Stop API/workers,
   back up DB/media and migrate 0014 before restarting server/mobile.
2. Check disabled delivery copy and normal old/new project behavior. Optional
   disposable-account file QA is in AUTH_RECOVERY.md; it sends no email.
3. Keep real delivery disabled pending an approved provider/channel plan and
   production privacy/security review. Continue remaining Phase 2 refresh/MFA,
   broker/lease renewal, isolation/monitoring/capacity gates before later AI work.

No paid APIs, paid infrastructure, real billing or subscription collection were
activated. Heavy rendering remains on the server; no private keys were put in mobile.
