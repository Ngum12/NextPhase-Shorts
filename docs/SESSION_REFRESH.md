# Session refresh — Phase 2 package 1

## Upgrade

Stop API/workers, back up DB/media, pull the reviewed change, migrate **0015**, then
restart API/worker/Metro. No new dependency/native module or reinstall is needed
solely for this package. Legacy access-only sessions retain their original expiry;
sign in again once to obtain a refresh pair. Real email remains disabled.

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
```

| Server setting | Default | Bounds / meaning |
|---|---|---|
| AUTH_ACCESS_MINUTES | 15 | 1–60; new JWT access lifetime |
| AUTH_REFRESH_DAYS | 30 | 1–30; absolute login-family lifetime |
| AUTH_REFRESH_IDLE_DAYS | 7 | 1–absolute; unused grant lifetime |
| AUTH_REFRESH_RETRY_SECONDS | 120 | 30–300; committed rotation recovery window |
| AUTH_REFRESH_IP_LIMIT | 120 | Positive; shared fixed auth-window IP budget |
| AUTH_SESSION_HOURS | 24 | Legacy helper only, not new access lifetime |

## Protocol and boundaries

Register/login return `access_token`, `token_type`, remaining `expires_in`,
`refresh_token` and remaining `refresh_expires_in`. Refresh credentials are opaque
256-bit capabilities, sent only in JSON POST bodies. Protect them like passwords;
never put them in URLs, analytics, logs or issues. Staging/production require HTTPS.

`POST /api/v1/auth/refresh` accepts `{refresh_token, rotation_key}`. Use a fresh
UUID4 for each logical rotation, durably saved BEFORE the request. Reuse that key
only to recover the same request. No bearer/cookie is required. The server locks
the owner, consumes the old grant, records the keyed rotation hash and commits a
replacement grant/access session. DB records contain domain-separated HMACs,
not plaintext refresh secrets. Replacement secrets use separate server-key domains,
allowing exact recovery without storing plaintext. JWT-secret rotation invalidates
both access and refresh credentials; plan re-login.

A consumed token with a DIFFERENT rotation key revokes its entire login family,
including all valid access tokens. Revocation commits before returning 401; other
device families remain valid. Matching old-token/key retries recover the same pair
only within the recovery window, while the successor is unused and replacement
credentials remain valid. A late matching retry fails without revoking newer
credentials. Recovery beyond the window requires reauthentication. A thief holding
BOTH old token and retry key can recover the pair inside that window: this bounded
recovery tradeoff is not proof of device identity.

Normal rotation permits old access until short expiry. Every access request checks
the DB session and live family. Logout-current revokes that family; logout-all,
password change/reset and account deletion revoke all families for that owner.
`POST /api/v1/auth/refresh/logout` takes `{refresh_token}` and revokes the family
even with expired access or a consumed grant. Unknown well-formed capabilities
also return 204. Shared IP/per-token budgets protect refresh and refresh-logout.

Migration preserves legacy rows with nullable indexed `AuthSession.family_id`.
There is no family foreign key on access rows: expiry cleanup is independent;
access rejects a missing family. Consumed grants remain through absolute family
expiry for replay detection. Auth maintenance deletes expired families in batches
of <=1,000 families, grants first; grant count depends on rotation activity. This
is not a global metadata quota (package 5).

## Mobile

One versioned SecureStore record holds the pair, expiry hint and pending key;
legacy raw-token records remain supported. Save intent before sending and the
replacement before use. Network/5xx/storage failures retain the durable intent;
definitive refresh 401 requires sign-in. Device time is only a proactive hint;
the server enforces expiry. Concurrent requests share one rotation. Generation
guards and serialized storage prevent late replies overwriting a newer login or
old screens borrowing another account's credential. A stable UI generation handle
avoids rotation triggering account-change effects that cancel active uploads.

Resolve current access before API calls, including upload chunks. Direct S3 PUTs
still have no API Authorization header/cookies. GET/HEAD and native download may
retry once; writes/multipart streams are never silently replayed. A write that
received 401 can renew credentials but requires an explicit UI retry; resumable
progress remains. Single-device logout uses refresh even with expired access;
offline logout retains credentials until revocation succeeds. All-device logout
and password change first obtain current access.

## Automated and focused device checks

```bash
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q
.venv/bin/python scripts/smoke_e2e.py
.venv/bin/python scripts/smoke_session_refresh.py
cd apps/mobile
npm test
npm run typecheck
```

The standalone proof uses its own DB/API/accounts and restarts after rotation,
then recovers the exact pair, checks reuse revocation, other-login preservation
and logout via a consumed token. Expired-access proof signs a past-expiry fixture
JWT with the disposable key; it does not wait 15 minutes or modify a real DB/clock.
Sanitized evidence is in ignored `.data/session-refresh-smoke-*`. Full HTTP smoke
includes this proof, so existing backend CI executes it automatically.

One Pixel acceptance after review/merge:

1. Sign out/in once; confirm your projects, then close/reopen Expo and confirm
   the session restores.
2. For quick local QA, set `$env:AUTH_ACCESS_MINUTES = "1"` in the API terminal
   before starting it; sign in again. Wait ~70 seconds, refresh My Shorts, then
   upload/resume a consented clip and render/save. Keep USB port forwards
   8000/8081 (8333 for direct local S3).
3. Sign out/in again; return API access lifetime to the 15-minute default and
   restart it after QA. No credentials or codes need to be shared.

Remote CI/native acceptance remain separate gates. No email, MFA, secret manager,
paid infrastructure or billing is activated. Dependency/legal gates remain open.
