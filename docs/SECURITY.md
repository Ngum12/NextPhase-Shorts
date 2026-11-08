# Security / privacy — gating checklist, not completed certification

### What Stage 1 already does

- Revocable, DB-backed JWT bearer sessions with required issuer/audience/expiry, current/all-session logout and authenticated password change; salted scrypt passwords; user-owned job/download filtering.
- Shared atomic auth attempt windows with HMAC identity keys, generic failed-login responses and strict socket-peer selection. See [auth limits and remaining risks](AUTH_SESSIONS.md).
- UUID-based storage paths; fixed command arguments (no `shell=True`); FFprobe media validation.
- FFmpeg runs in a separate worker process / Docker service; production Docker worker uses unprivileged user.
- Upload size and format checks, output <= 60 seconds, env-based private JWT secret.
- Owner-only project deletion immediately revokes access/claims, with retryable
  private-volume cleanup; backups and full retention remain open.
  See [deletion boundaries](PROJECT_DELETION.md).
- Conservative per-account source/render reservations and bounded accepted output
  files; global physical disk, spooling/orphan and production quota controls remain.
- Explicit versioned uploader attestation (not verified rights), restricted media
  profiles and file-only FFprobe/FFmpeg input protocols. Full antivirus/sandbox,
  rights verification and legal/privacy review remain open.
- Billing disabled, AI model disabled, no secret keys in app.

Migration-managed PostgreSQL, private-volume resumable uploads and shared auth
limits are implemented; they do not satisfy the remaining production controls.

### MUST implement before accepting real public traffic

- HTTPS/TLS, WAF/reverse proxy upload body limit, user/email verification, broader abuse/edge rate controls, optional MFA, verified account recovery and session refresh.
- Secret manager, signed short-lived object URLs, private cloud object storage, virus/decompression defenses, media fingerprint checks and limits on codecs, resolution and upload duration.
- Defense-in-depth resource limits (workers CPU/RAM/process time, quotas and isolation), SSRF/network egress restriction, sandbox no arbitrary execution from AI outputs.
- Media ownership/consent, rights verification, lawful content/misinformation handling, moderation, appeals and reporting mechanisms; do not build misleading impersonation/voice clones without permission.
- Data deletion, retention transparency, GDPR/other local privacy review, opt-in third-party AI sending, privacy policy, terms of service, backups and incident playbook.
- Auditable payment events, server-side verified webhooks, no browser-asserted payment success; idempotency, reconciliation, cancellations, refunds and chargeback handling.
- Logs cannot contain full customer videos, full ASR transcripts, personal payment information or secret tokens; least privilege and rotation.

**Important:** Stage 1 is a developer prototype, not production-hardened; don't expose it as-is to the public internet.

Optional S3 storage and exact-key expiring signed GETs are implemented; the default
remains local. API downloads keep bearer credentials on-origin. Signed links are
capabilities and cannot be recalled by logout or tombstoning alone; physical
removal/expiry limits them. Private bucket policy, TLS, log redaction, version-aware
erasure, orphan/lifecycle controls and provider isolation remain deployment gates.
See PRIVATE_OBJECT_STORAGE.md; never treat a successful bucket HEAD as privacy proof.

Opt-in direct PUT capabilities are exact-key/length/checksum scoped to temporary
incoming objects. The API rehashes and privately seals before acknowledging;
client capabilities never target verified parts or accepted media. Expiry-aware
terminal cleanup/rescans and three-source admission reservations limit retained
staging. Capability revocation, late writes, provider policies, abuse/load and
full account/backup erasure remain bounded as documented in DIRECT_UPLOADS.md.

Unknown-orphan deletion is offline-only with minimum 24-hour grace, DB/reference
protection, namespace-bound preview digest, bounded inventories and metadata
rechecks. It is not an online race-proof collector or automatic saved-project
expiry. See RETENTION.md for writer shutdown, backup and deletion boundaries.

Account deletion requires current-password verification, owner locking and a durable
receipt; it revokes sessions/claims before retryable media cleanup. Receipt recovery
is an expiring opaque capability, not identity recovery. Operational records, backups
and device exports remain. See ACCOUNT_DELETION.md for race/capability boundaries.

Worker containment adds credential-reduced decoder environments, Linux parent-death/
CPU/open-file limits, POSIX render-group teardown and a strict Compose cgroup guard.
Read-only/unprivileged containers still share trusted media and network access; this
is not a per-tenant exploit sandbox. Managed Docker here lacks cgroup enforcement;
production host acceptance is required. See WORKER_RESILIENCE.md.

Worker pulse metadata and aggregate queue snapshots are local operator tools; no
public metrics/admin route is added. Minimal `/ready` exposes no dependency details.
Validated structured worker events omit arbitrary messages, exception text and
credentials; correlation UUIDs and all operational logs remain private. This is not
a global logging/retention certification. See OPERATIONS.md for heartbeat boundaries.

Local email-action proof handling is implemented with delivery off by default and
a file-only development/test adapter. It is forbidden in staging/production and
not proof of actual email ownership. One-use credential-bound hashes, owner locks,
revocation, secret-free validation and private inbox permissions are tested. Local
message files contain codes/recipients and are outside media erasure; protect/remove
disposable test messages. Real delivery/enforcement/outbox/privacy gates remain open.
See AUTH_RECOVERY.md; no SMTP/provider or unauthenticated recovery bypass enabled.

Package 1 adds opaque refresh rotation, short access tokens, owner-locked family
reuse detection and committed revocation across logout/reset/deletion. A bounded
same-key recovery window handles lost replies; consumed hashes remain to absolute
expiry. Mobile uses SecureStore, durable intent and generation guards. See
SESSION_REFRESH.md for retry/theft/cleanup boundaries. HTTPS, real email, MFA and
production security gates remain open.

Package 2 implements disabled-by-default fixed-origin Resend delivery with a
separate sender, encrypted bound outbox, owner-ordered/fenced claims, stable
idempotency, conservative shared attempt caps, expiry/terminal payload erasure and
credential/deletion cancellation. Opt-in verified-email admission rejects local
test proofs while keeping sign-in/recovery/deletion and existing-project reads
reachable. Provider acceptance is not inbox delivery; in-flight mail cannot be
recalled. Real inbox/provider/privacy/Pixel acceptance remains unobserved. See
EMAIL_DELIVERY.md for activation, key rotation, external copies and cleanup scope.

Package 3 adds strict JSON-only Valkey/Arq signals (no pickle/user commands),
transactional DB recovery authority, short fenced renewal with absolute deadlines,
bounded transient attempts/dead letters, and preserved older-writer cleanup bounds.
Required decoder mode combines unprivileged/cgroup checks, Landlock input/attempt
filesystem rules and seccomp network/selected escape denial. No Docker socket is
mounted in application services. Unsupported hosts fail closed; this managed host
does not pass cgroups/Landlock, so production containment is not accepted. Shared
kernel/runtime paths are not a VM or exploit certification. Native development
mode remains explicitly weaker. See QUEUE_RELIABILITY.md for exact limits, TLS,
RPO/reconciliation and remote-store late-write/erasure boundaries.

Package 3 owner acceptance update (2026-11-08): supplied Docker Desktop report
shows unprivileged user/cgroup/filesystem/network protections enforced and ready
true; owner confirmed protected-stack Pixel render/save/playback and a healthy
operations report. This does not change the managed cloud host's unsupported
status or constitute a production security certification.

Package 4 adds fixed-schema correlated observations, content-free request/error
logs, operator-only OTLP/Prometheus exports and explicit partial-cost coverage.
Mounted secret files reject ambiguous values, unsafe types/links/permissions and
oversize input; values are not copied into decoder environments or logs. Restart
consumers on rotation; JWT rotation deliberately requires re-login. External vault,
collector/alert routing, edge logs, provider billing reconciliation, metadata
retention and privacy/security signoff remain deployment/capacity gates. See
MONITORING_SECRETS_COSTS.md; no public metrics endpoint or telemetry network sender.

Package 5 adds owner-then-global admission locking, shared retained/scratch budgets,
worker concurrency/free-space checks, pre-parser body caps and bounded API execution.
Intake reservations remain charged after crashes until explicit stopped-writer
recovery. Strict decoder writes are narrowed to one precreated file with hard
RLIMIT_FSIZE. Trace/stopped-worker retention is bounded, not full metadata erasure.
A disposable PostgreSQL/media restore and 100-request/steady-soak exercise are
implemented. See CAPACITY_SECURITY.md and SECURITY_REVIEW_2026-11-08.md: unresolved
17 npm findings, image/legal/privacy/backup-journal and real staging quotas remain
public-launch blockers, not accepted production risks.

Package 6 preparation resolves the historical mobile npm graph to zero current
advisories via SDK 58 and reviewed scoped tool patches, with async-upload/legacy
Save API fixes and SDK/native-config/bundle tests. SDK 58 Pixel acceptance remains
open. Docker API now defaults to loopback; private image inventory does not imply
a completed vulnerability/legal scan. The owner's package 5 updated strict-host/
render/Save/playback checks passed. Remaining engineering/owner/provider gates and
unpublished policy draft are in STAGING_BLOCKERS.md / PRIVACY_TERMS_DRAFT.md; no
public staging, paid resource, real mail, billing, AI or legal signoff was enabled.


Independent local restore protection records encrypted write-ahead deletion/
revocation intentions outside DB/media snapshots. Offline replay verifies the
full chain against a separately retained current checkpoint, revokes all restored
credentials/passwords, reapplies tombstones and leaves an explicit access hold.
A 120-second minimum retirement interval precedes release. API staging/production
requires a configured ready journal; local development is opt-in. This cannot
automatically detect arbitrary manual DB rollback or replace old-host fencing,
immutable/offsite journal/key custody, encrypted backups or complete remote erasure.
See RESTORE_JOURNAL.md for failure, privacy and recovery boundaries.
