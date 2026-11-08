# Phase 2 package 2 — Resend and verified email

## State and prerequisites

Delivery is **disabled by default**. This package implements an opt-in Resend
transport, durable encrypted outbox/retries, verified-upload policy and mobile
states. Local automation never contacts Resend: a separate disposable fixture
intercepts the fixed provider URL with MockTransport. Actual provider/inbox/Pixel
acceptance and provider/privacy approval remain separate gates.

Owner reports `auth.techskillnow.com` and its DKIM/two Forge CNAME records verified
in Ireland (`eu-west-1`), and a sending-only API key prepared privately. These are
owner-supplied dashboard results, not an independent DNS or inbox test. Receiving
is unnecessary; preserve existing root website, MX, SPF, DKIM and DMARC records.
Sender: `NextPhase Shorts <noreply@auth.techskillnow.com>`.

Resend API contract references: https://resend.com/docs/api-reference/emails/send-email
and https://resend.com/docs/dashboard/emails/idempotency-keys . This environment
could not access the provider site (proxy Forbidden); current free allowance,
idempotency retention, Forge behavior, privacy/terms and deliverability must be
checked in the actual account before activation. Do not treat a Google summary
or this implementation as approval of provider terms or a guarantee of free use.

## Upgrade and secret preparation (no sending)

Stop API, render/mail workers and Metro; back up DB/media. Pull the reviewed merge.
New dependency `cryptography==50.0.2` provides authenticated encryption; its bundled
notices/transitive inventory are retained. Run from repository root:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.txt
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe scripts/configure_auth_email.py
```

Migration **0016_email_outbox** preserves accounts, sessions, local proof meaning,
uploads/jobs/media. Helper asks for the API key through a hidden terminal prompt,
sender, and **one inbox you own**. It writes ignored `.data/auth-email-env.json`
with sending and enforcement **false**, QA caps 5 attempts/day and 20/month, and
a separate generated encryption key. Re-running preserves existing encryption
keys. It never calls a provider. Never print/upload/commit that file. POSIX uses
a 0600 replacement file; Windows requires a private current-user NTFS folder/ACL.
Back up encryption keys privately. Existing DB backups can retain old ciphertext;
include key/backup retention in the production privacy policy.

Load this file in both API and **separate mail-worker** terminals, without displaying
its contents:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
(Get-Content .data\auth-email-env.json -Raw | ConvertFrom-Json).PSObject.Properties |
    ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name, [string]$_.Value, "Process") }
$env:PYTHONPATH = "apps/api"
```

Keep existing media/S3 settings for API/render processes. The sender requires no
media mount. A process cannot inherit settings set in a different PowerShell
window. Do not load mail secrets into Metro/mobile. With sending false,
`python -m app.mail_worker` exits without contacting Resend. No private key should
ever be placed in `EXPO_PUBLIC_*`, a CLI argument, chat, screenshots or shell history.

## Focused real-inbox acceptance — only after review/activation approval

Confirm Free plan, current provider limits, authenticated sender, owned recipient
and provider terms first. The QA helper restricts delivery to that single recipient
and 5 attempts/day, 20/month. Do not upgrade a paid plan. Other applications using
the account consume provider quota too; local limits cannot account for their sends.

1. In API and mail-worker terminals, after private configuration loading, explicitly
   set `$env:AUTH_MAIL_SEND_ENABLED = "true"`. In API also set
   `$env:AUTH_REQUIRE_VERIFIED_EMAIL = "true"` for this focused test. Start API with
   the usual `--no-proxy-headers` command and sender with:

   ```powershell
   .\.venv\Scripts\python.exe -m app.mail_worker
   ```

   The render worker stays a separate process. Restart Metro in `apps/mobile`.
   Keep USB 8000/8081 (8333 if direct local S3) forwards.
2. Use a disposable account with the **exact owned recipient address**. Account →
   Email confirmation → Request email code. Check inbox/spam and enter the one-use
   code in the app. Confirmation works after sender acceptance is committed; a
   message can arrive just before that commit, so retry once if needed. Never
   share a code. Account must say **Email address confirmed**, not local test proof.
3. New uploads/resumes must be blocked before real verification and work afterward.
   Render/save one consented video. Existing projects/read/download/deletion and
   sign-in/recovery remain accessible when unverified; pending upload files remain.
4. Forgot password: receive a reset code, set a new password, verify old sessions
   are rejected and the new password works. Code reuse must fail. Do not rerun the
   whole manual regression suite; automated tests cover races/retries/isolation.
5. Stop sender/API, reload private QA configuration (sending false), and restart
   normal API/render/Metro as needed. This also restores enforcement false for
   normal preview accounts. Do not leave real sending active unintentionally.

Private operator report (no addresses/codes/keys):

```powershell
.\.venv\Scripts\python.exe -m app.mail_worker --report
```

Provider acceptance is not inbox delivery. If requests say queued but no mail
arrives, inspect report/state and Resend dashboard privately. Never paste provider
responses, recipient lists or credentials. A report's budget dates matter: old
counts are for those UTC windows, not necessarily today's current counts.

## Delivery and security contract

- Requests retain generic 202 acceptance for unknown accounts, capacity, disabled
  delivery or preparation failure; they do not assert an account exists or delivery
  succeeded. Real preparation is a short DB transaction (not constant-time account
  lookup). Existing socket-IP/email/code limits and <=3 pending messages per owner
  apply. Unknown accounts create no outbox. No automatic signup email is sent;
  the owner explicitly requests verification from Account.
- Commit action hash and encrypted envelope together. Fernet authenticates the
  entire envelope; plaintext includes row/action/owner identities, recipient/code
  and a frozen provider message. Bindings, current credentials, expiry and deletion
  are rechecked before dispatch. No plaintext recipient/code in outbox columns,
  logs or responses. `users.email` remains existing account data, not newly encrypted.
- Resend calls use only `https://api.resend.com/emails`, verified TLS, no redirects,
  bounded IO timeouts/response size and `Idempotency-Key: auth-<outbox UUID>`. Frozen
  content/key survive retries and process crashes. Idempotency is provider-scoped;
  acceptance/inbox guarantees still depend on actual provider behavior and retention.
- Sender owner-locks before claiming, uses a 90-second fenced lease and commits
  reservation before network IO. Network never holds owner locks. Retry 429/408/409,
  network and 5xx failures with bounded exponential delay/Retry-After and <=5 actual
  attempts, all within action expiry. Other rejections terminate safely; provider
  bodies/exception text are discarded. A stale claimant cannot publish acceptance.
- One DB budget serializes send reservations across sender processes: defaults
  20/day, 500/month, configurable up to 100/day and 3000/month as conservative
  application caps, **not current provider-plan guarantees**. Retries, crashes and
  reservations with no send can consume attempt budget. UTC day/month counters
  survive restart; backward window changes fail closed. At most one reservation
  per second. Quota/throttle delays do not increment attempts; expired codes cancel.
- Accepted/terminal payloads are erased immediately. Expired ciphertext is wiped
  in bounded <=1,000-row cleanup batches; terminal metadata is eligible for deletion
  one day after proof expiry. Auth-action cleanup respects outbox FKs. Render auth
  maintenance also cleans expired mail even when sender is disabled. Operators can
  run `python -m app.mail_worker --cleanup`; stopped processes cannot promise a
  wall-clock purge SLA. Provider copies/backups/recipient inboxes remain external.
- Password change/reset/account deletion cancel queued/claimed messages and wipe
  their payload in the same owner transaction. An already in-flight provider call
  can still deliver after revocation; its code is unusable and stale completion is
  fenced. Outgoing messages cannot be recalled. Turning sending off requires
  restarting sender/API with the flag false; already accepted mail remains.
- Only actions tagged `resend` with durably accepted outbox delivery can establish
  real email verification. Old `local_file` proofs stay local; they cannot be
  promoted by migration or by changing config. Cross-channel redemption fails.
  Reset preserves projects and revokes all access/refresh families for that owner.
- `AUTH_REQUIRE_VERIFIED_EMAIL=true` gates new multipart uploads, resumable session
  creation/parts/completion and direct grant/commit routes. It does not prevent
  login/refresh/recovery/deletion or reads of existing projects. Already queued
  jobs may finish. Production must explicitly enable policy after channel QA;
  this preview defaults false and is not yet a public production deployment.

## Encryption-key rotation and deployment

`AUTH_MAIL_ENCRYPTION_KEYS` is a comma-separated Fernet key ring, primary first.
Never reuse `JWT_SECRET`. For planned rotation, stop issuance/sender, retain
`new,old` in both API and sender, and run `python -m app.mail_worker --reencrypt`.
If `next_after` is returned, repeat with `--after <that UUID>` until null. Each
batch visits <=1,000 payloads. Then remove the old decrypt key only after confirming
all live payloads are rotated; preserve recovery keys for retained backups under
your retention policy. Restart with the new ring. Missing/corrupt keys terminate
those messages as payload_unavailable; users must request new codes. Never decrypt
messages into operator output or replace keys casually by re-running setup.

Optional Compose sender: `docker compose --profile email up -d mail-worker` after
reviewed config/migration. Profile is off by default, runs unprivileged/read-only,
has no media mount and no inbound port. This environment did not deploy it to a
production host; rendered-worker cgroup enforcement remains a package 3 gate.
Use role-scoped environment/secrets and an approved trust bundle for proxies;
do not disable TLS verification. Sender/domain/API-key rotation, provider terms,
bounce/complaint handling, incident procedures and end-to-end privacy review must
be accepted before public traffic; this package does not certify production safety.

## Automated evidence

Backend tests cover atomic encrypted issuance, failed encryption, concurrency/
stale claims, network/rejection/rate failures, exact retry bodies/keys, caps,
revocation, expiry/cleanup/key rotation, legacy preservation and verified routes.
Client tests cover delivery capability/policy and prior public-action/session rules.
`scripts/smoke_email_delivery.py` uses a private disposable DB/API and separate
sender process with a **local-only mock transport**. It restarts API before send,
kills the sender after simulated provider acceptance, advances only the stopped
fixture's lease, recovers the same message, verifies gated admission and reset/
refresh revocation, preserves another account, checks logs and removes private
fixture files. `smoke_e2e.py` includes it; other smokes explicitly disable real
sending regardless of inherited email settings. No automated test sends real mail.
