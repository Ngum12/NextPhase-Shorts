# Phase 2 increment: revocable sessions and authentication limits

This is a partial auth-hardening increment. Email verification, verified password
recovery, refresh-token rotation, security notices and admin MFA remain open.
No mail service, paid API, cloud infrastructure or real billing is activated.

## Upgrade an existing Windows installation

Stop API, worker and Expo before pulling. Preserve your database and media backup;
use the actual configured DB path if it differs from the default below.

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-auth-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm ci
npm run typecheck
npm run test:uploads
npm run test:auth
```

Migration `0005_auth_sessions` adds two tables/indexes. Accounts, password hashes,
completed videos, upload offsets/parts and pending mobile copies remain intact.
Existing bearer tokens lack the new session ID and **require one new sign-in**.
Use the same account/password; creating another account hides the original owner's
projects and pending uploads. Existing 10-character passwords still work at login.
New registrations and password changes require 12–128 characters.

Restart the API with forwarded headers disabled, in one terminal at the repo root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000 --no-proxy-headers
```

In another root terminal, set `$env:PYTHONPATH = "apps/api"` and run
`.\.venv\Scripts\python.exe -m app.worker`. Start Expo from `apps/mobile` as in
[development instructions](DEVELOPMENT.md), using SDK 54 Expo Go and USB forwarding
for ports 8000 and 8081. Do not accept a different Metro port without forwarding it.

Compose: stop API/worker, back up PostgreSQL and media, build, run one migration
process (`docker compose run --rm migrate`), then `docker compose up -d --wait`.
Do not delete volumes. Downgrade requires stopped services, prior code and a verified
backup. No token migration or implicit schema changes happen on API startup.

## Session semantics

- HS256 bearer tokens require issuer, audience, subject, issued-at, expiry and a
  random session ID. Each request also checks the DB session's owner, expiry and
  revocation state. The DB stores SHA-256(session ID), never the bearer credential.
- Login/register return `access_token`, `token_type=bearer`, `expires_in` in seconds
  and `Cache-Control: no-store`. Default expiry is 24 hours; no automatic refresh.
- `POST /api/v1/auth/logout` revokes the current session; `logout-all` revokes all
  current sessions for that account. Both return 204, require a valid bearer and
  persist across API restarts. A previously revoked token gets 401.
- `POST /api/v1/auth/password` accepts `current_password`, `new_password`, verifies
  the current scrypt hash, updates it and revokes all sessions in one transaction.
  Wrong current password returns 400 without invalidating the valid bearer.
- Password changes and login issuance serialize on the owner row. A password
  request rechecks revocation after acquiring that lock. Other requests already
  authenticated/in flight can finish; revocation does not cancel render jobs or
  interrupt an existing download. Future requests require a valid session.
- Mobile stores credentials in SecureStore, checks saved tokens on startup, clears
  the originating credential on authenticated HTTP/native-download 401 and routes
  to sign-in. A delayed response for an old token cannot clear a newer login.
  Login failures are separate from authenticated-request expiry handling.
- Sign out and sign out all require a server connection. Network failure retains
  the credential so the user can retry, rather than falsely reporting revocation.
  If secure-storage removal fails after server revocation, the saved token remains
  unusable and startup validation will reject it. Re-sign-in uses the same owner,
  so private pending upload journals remain recoverable until their normal expiry.

## Persistent fixed-window limits

All API instances share atomic DB counters. Defaults, configurable in `.env`:

| Setting | Default | Effect per window |
|---|---|---|
| AUTH_SESSION_HOURS | 24 | Session TTL, allowed 1–72 hours |
| AUTH_WINDOW_SECONDS | 900 | Fixed window length, allowed 10–3600 seconds |
| AUTH_LOGIN_ACCOUNT_LIMIT | 5 | Login attempts per normalized email |
| AUTH_LOGIN_IP_LIMIT | 30 | Login attempts per socket peer; also separate password-change IP budget |
| AUTH_REGISTER_IP_LIMIT | 10 | Registration attempts per socket peer |
| AUTH_PASSWORD_LIMIT | 5 | Password-change attempts per account |

Successful and failed attempts count. 429 includes integer `Retry-After`; denied
attempts do not extend the window. Expired windows reset atomically. A blocked
peer does not create additional account buckets. Stored keys are HMAC-SHA256 of
purpose and identity with the backend JWT secret; plaintext IPs/emails aren't
stored in the rate table. Unknown email login still performs one dummy scrypt
verification and returns the same 401 detail as a wrong password.

The worker removes expired auth sessions and counters during its maintenance
cycle (at most once a minute between renders, potentially delayed by an active
render). Expiry is enforced even before cleanup. This is not a WAF: a targeted
account can be temporarily exhausted, shared NAT clients share an IP budget,
and registration's existing 409 response still exposes an existing account.
Further abuse/privacy policy work remains. Malformed bodies get validation 422;
edge request/body/rate limits must cover traffic before application validation.

Use `--no-proxy-headers` as supplied by Docker/README/this guide. Client-supplied
X-Forwarded-For must not select the rate key. A production reverse proxy requires
an explicitly reviewed sanitized trust boundary; with these defaults all proxied
requests share the proxy's socket IP budget. Do not simply trust arbitrary headers.
TLS, secret management/rotation, verified email delivery/recovery, MFA, deletion,
production edge controls and security review are still required. There is no
unauthenticated password-reset bypass and no claim that email ownership is verified.

## Required physical Pixel acceptance after merge

Use only a test account and consented/synthetic media. These new auth checks have
not been executed on a physical device by the cloud agent.

1. Sign in again with the existing account; old projects/downloads must remain.
2. Sign out, sign in again and confirm server connectivity errors are clear if
   disconnected. Sign out all sessions; a second session for that account should
   receive 401 on its next request.
3. Under Account → Change password, try a wrong current password; remain signed in.
   Change it correctly; return to sign-in. Old password fails; new one succeeds.
4. Pause an upload, sign out/in to the same account, reopen New Short and resume.
   Finish render/download and play the MP4. Signing out must not erase the original.
5. Force-stop/reopen Expo with a valid saved session; it restores after validation.
   After revocation elsewhere, a refresh/reopen should return to sign-in.

The smoke command uses the documented default auth budgets. External `--base-url`
runs require those budgets and enough unused peer capacity; wait out the window
when repeating against a shared development API. Isolated smoke overrides its own
auth budgets and never changes the caller's database.

Automated tests cover DB revocation/expiry/claims, old-password compatibility,
password-change/revocation races, concurrent limits, migration preservation,
JS storage/request races and actual HTTP/API-restart behavior. They do not replace
native SecureStore, device navigation or real multi-device acceptance.
