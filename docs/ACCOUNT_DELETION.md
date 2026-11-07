# Account deletion in the developer preview

Account → Delete account requires the current password and an explicit destructive
confirmation. This permanently disables that account in the app. It is not a
complete personal-data erasure or production privacy-compliance implementation.
Test with a disposable account, not your main creator account.

## What happens

POST `/api/v1/account/delete` with bearer authorization and JSON
`current_password`, `receipt_key` (a cryptographically random UUIDv4) returns 202
`{"status":"account_disabled","media_cleanup":"scheduled"}` only after commit.
A single owner-locked transaction revokes every session and render claim, hides
all projects, terminates upload intents, replaces the account email/password hash,
and scrubs project/upload display names, source hashes and source/output paths.
Admission, upload commit and worker claiming recheck the disabled owner. Previously
authenticated requests already in progress may finish; signed storage capabilities
remain usable until expiry/object removal. Never promise recall of downloaded bytes.

The original email can register a new, unrelated account; it cannot regain the
old projects. Operational tombstones remain: UUID relationships, rights statements,
request fingerprints, timestamps, size/cost/attempt metadata, session hashes,
HMAC abuse counters and direct grant records. Backups may still hold older values.
There is no account restoration action or unauthenticated password-recovery bypass.

## Lost responses and phone data

The phone saves an owner-bound random receipt key in SecureStore before requesting
deletion. Passwords/tokens are not saved in that intent. A network error or 401 alone
is not deletion proof. POST `/api/v1/account/deletion-receipt` with only `receipt_key`
recovers the coarse status without a login. It returns no email/account identity,
is rate limited by socket peer, uses no-store responses and expires after seven
days. The server stores only its SHA-256 hash. Keep the capability private; redact
request bodies in any future proxy/diagnostic logging. Unknown/expired keys return
404, not proof that deletion failed. Lost app data loses this recovery capability.

Use **Finish account deletion** on the sign-in screen after a restart. Only explicit
server confirmation permits removal of that owner's private pending upload copy
and journal. Storage/cleanup failures retain the receipt for retry. A late response
cannot clear a newer login. Other accounts' intents and original/gallery videos are
preserved. Saved/shared exports and legacy download caches are not removed.
Recovery after seven days requires operator investigation; no support service or
verified email delivery is configured in this preview.

## Durable server cleanup

Worker maintenance (between renders) processes at most five account records each
pass and resweeps previously cleaned owners. The durable deadline waits at least
`UPLOAD_PART_TIMEOUT_SECONDS + 90` seconds, and longer than known render leases or
signed upload grants plus 30 seconds. This is conservative fencing, not a universal
bound on external in-flight provider writes. Resweeps handle late artifacts.

Canonical owner local trees and `media/<owner>/`, `uploads/<owner>/` S3 prefixes
are removed. Other owners are preserved; owner symlinks/junctions are refused.
S3 removal uses existing bounded batches/private nonversioned-store checks.
Namespace mismatch/unknown historical namespace, provider or filesystem failure
keeps cleanup pending and retries. All recorded namespaces must match the configured
store; operator reconciliation is required for a historical multi-store account.
Unrecorded historical buckets, versions, replicas and backups are outside proof.
`media_cleanup=verified` means the configured recorded media trees were swept,
not that every personal datum or every external copy was erased permanently.

For a configured server, `PYTHONPATH=apps/api python -m app.account_deletion` performs
a bounded maintenance pass; this command really removes due disabled-owner media.
It is separate from the nondeleting `app.retention` preview. Do not invoke it with
unreviewed database/store settings. No live owner account was deleted by development
validation; tests use synthetic disposable identities and stores.

## Upgrade and Windows acceptance

Stop API and worker, back up DB plus local/S3 media, then from repository root:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm run typecheck
npm run test:account
npm run test:auth
npm run test:uploads
npm run test:exports
```

Migration **0012_account_deletion** preserves existing active accounts/projects and
adds nullable disablement plus the durable receipt/cleanup table. No new dependencies
or paid services. Restart API, worker and Metro; USB reverse 8000/8081 (8333 for
local S3). Each server terminal still needs its server-only S3 configuration.

On Pixel, create a disposable account, upload your own test clip, and optionally
pause another upload. Wrong password must preserve access. Delete with correct
password: all sessions lose access, other accounts remain usable, original/saved
videos remain. Test lost-response recovery without clearing app data. Physical
Pixel/iOS acceptance of these new controls remains outstanding until reported.

`smoke_account_deletion.py` starts its own temporary database/API, uploads synthetic
media for two accounts, disables one, restarts the API, recovers its receipt and
checks revocation/other-owner preservation. After stopping only its own writers it
advances that synthetic cleanup deadline and verifies removal. This does not claim
observation of the real waiting interval. The ordinary HTTP smoke also runs it;
the disposable S3 smoke repeats it with the local object service.
