# Local authentication recovery and email proof preview

**No email provider is configured or contacted.** Delivery defaults to disabled.
The only implemented adapter is an opt-in private local-file inbox for development
and disposable-account QA. It is rejected in staging/production. This validates
code handling; it does not establish real-world email ownership or complete the
production recovery/verification gate. No funds, provider account or new dependency.

## Upgrade

Stop API and workers, back up DB/media, pull and run migration **0014_auth_actions**.
It adds nullable email-proof fields and one action table; no legacy account is
invented as verified. Existing passwords, sessions, project paths, rights and
paused upload state remain. Verification is **not enforced** for preview login or
uploads; existing accounts are not locked out.

From the repository root on Windows, with services stopped:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-auth-recovery-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm run typecheck
npm run test:recovery
```

Use your PostgreSQL backup process instead of copying a SQLite file for that setup.
No pip/npm reinstall or new native module is needed. Restart API, worker and Metro
for the updated screens; keep current S3 settings and USB forwarding when used.

## Default behavior and local opt-in

GET `/api/v1/auth/recovery-capabilities` returns `delivery: disabled` and
`verification_enforced: false` by default. Forgot password and Account → Email
confirmation explain the disabled preview. Requests return generic acceptance
but issue no code; confirmation returns 503. No debug code is returned in API
responses and no unauthenticated password-reset bypass is provided.

For native local development QA only, set this in the **API** PowerShell window
before starting it, from repository root:

```powershell
$env:AUTH_MAIL_BACKEND = "file"
$env:AUTH_MAIL_DIR = Join-Path (Get-Location) ".data\auth-mail"
```

Keep APP_ENV as local development/test. Do not change a staging/production
installation's environment to evade the guard. There is no SMTP/HTTP-provider
adapter to enable. `AUTH_MAIL_DIR` must be outside media storage and must never be
served publicly or committed. The server creates the leaf directory mode 0700 and
files 0600 on POSIX, rejecting an unsafe link or existing broadly accessible inbox.
On Windows those POSIX modes are not ACL guarantees: use a private current-user
NTFS folder, not a shared directory. Containers need a separately private writable
inbox if tested there; do not weaken worker filesystem/resource protections.

Additional server-only options:

| Setting | Default | Bound |
|---|---|---|
| AUTH_MAIL_BACKEND | disabled | disabled / file; file only development/test |
| AUTH_MAIL_DIR | sibling auth-mail beside media | private, outside media |
| AUTH_ACTION_MINUTES | 15 | 5–30 |
| AUTH_ACTION_EMAIL_LIMIT | 3 | 1–20 per existing auth window |

The existing fixed-window socket-IP limits also apply. A local request schedules
best-effort after-response delivery: durable action commit precedes atomic private
message publication. A crash between them can lose delivery. Failures keep generic
responses and safe logs; no durable provider outbox or delivery guarantee is claimed.
Retrying can prepare another valid code; successful redemption consumes competing
codes as described below. The feature cannot be enabled from EXPO_PUBLIC variables.

## Disposable-account Pixel check

Use a new test account, not your main account, and remember its password.

1. With delivery disabled, verify the screens accurately show that no code can be
   sent. Enable local-file mode in the native API process and restart it for QA.
2. Sign in to the disposable account. Account → Email confirmation (local preview)
   → Request private test code. It always targets that signed-in account's email.
3. Privately open the newly prepared message on your PC. It contains recipient,
   purpose, expiry and a 43-character code. Check it belongs to your test account:

   ```powershell
   cd C:\Users\Ngum\NextPhase-Shorts
   $mail = Get-ChildItem .data\auth-mail\*.json |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
   notepad $mail.FullName
   ```

   Do not paste/upload this message or code into chat, screenshots, issues or logs.
   Enter the code in the app. Account should say **local test confirmed**; this is
   deliberately not a claim of actual email delivery/ownership.
4. From Forgot password, request a code for that test email, privately read the
   new reset-purpose message and choose a new 12+ character password. Enter a wrong
   code first: no password/session change should occur. With the correct code,
   all sessions for that account are revoked; old password fails and new one works.
5. Reusing the code fails. The same account/projects and saved uploads remain after
   sign-in; other accounts and original/gallery/shared files remain unaffected.
   If a response is lost, try the new password or request another code; a network
   failure is not proof of success. Codes/passwords are not persisted by the app.
6. Turn local delivery off by stopping the API, setting
   `$env:AUTH_MAIL_BACKEND = "disabled"`, and restarting. Keep private inbox contents
   protected and remove only your disposable test messages when finished.

Messages contain raw proof codes and recipient addresses. They are a local test
artifact **outside project/account media erasure**; no automatic inbox-file purge
is implemented. Do not use this adapter for public customer traffic or as a real
email verification service. Short-lived DB action records are separately removed
in bounded batches by existing worker auth maintenance after expiry.

## Protocol and security scope

- POST `/api/v1/auth/password-reset/request` accepts `{email}` and returns 202
  `{status: accepted}` for known, unknown, disabled or failed-delivery cases. The
  API does no account lookup before that response; local background work handles
  issuance. Response shape is uniform, not a production constant-time guarantee.
- POST `/api/v1/auth/email-verification/request` requires a live bearer; email is
  taken from that account, not a client-supplied target. Already-confirmed accounts
  need no new proof. Background work rechecks live session/owner under its lock.
- POST `/api/v1/auth/password-reset/confirm` accepts `{code,new_password}` and
  returns 204 only after password update, code consumption and all-session revocation
  commit. It issues no JWT and preserves projects/uploads. No automatic login.
- POST `/api/v1/auth/email-verification/confirm` accepts `{code}` and returns 204
  after recording local method/time. It never treats a reset code as a verification
  code or gives a session. Existing email-proof state stays explicit and method-tagged.
- Codes are 256-bit random capabilities, valid 5–30 minutes, stored as SHA-256 hashes
  in the DB. A separate HMAC binds the account UUID, current email and password hash
  to the server secret. Secret rotation invalidates old actions. No raw code, email
  or password is stored in the action table; local inbox files are the stated exception.
- Owner locking serializes redemption with password changes/deletion. Password reset
  and authenticated password change invalidate all pending action purposes; email
  confirmation consumes verification proofs. Deletion invalidates actions and scrubs
  proof fields. Re-registering an email creates a new owner that old codes cannot recover.
- Separate socket-IP/email/code HMAC rate windows bound requests and confirmations.
  Used/expired/unknown/credential-mismatched codes all return the same 400 detail.
  Auth validation responses are sanitized 422/no-store, without echoing input secrets.
- Public recovery calls use no bearer/cookies; their errors cannot expire a newer
  login. Authenticated request 401s retain existing originating-token guards. Password
  reset may revoke server sessions while in-flight requests or signed storage links
  remain effective until their existing completion/expiry boundaries.

Production still needs owner-approved real email delivery, sender/domain policy,
durable encrypted outbox/cleanup, verified channel enforcement, notifications,
TLS/edge abuse controls, recovery/privacy review, refresh/MFA and incident procedures.
Never promote local_file proof state into production email-owner authority. Preserve
separate development/staging/production databases/secrets. No provider was activated.

The default HTTP/S3 smokes force delivery disabled in their own API. A separate
`smoke_auth_recovery.py` fixture explicitly enables only its private temporary inbox,
restarts its API, confirms one-time reset/session isolation, checks secret-free logs
and removes all temporary code files. It uses no real email addresses/provider and
no existing account DB. Native Windows/Pixel acceptance of new screens remains open.
