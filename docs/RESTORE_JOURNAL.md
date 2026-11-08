# Independent security journal and offline restore gate

This increment protects **operator-controlled restores** from forgetting deletion
and revocation requests made after a snapshot. It is not automatic detection of
an arbitrary manual DB rollback, immutable/offsite storage, backup encryption or
a production disaster-recovery certification. Never expose a restored target
before replay/release. A copied old journal plus a copied old checkpoint cannot
prove freshness; independently retain the **current** checkpoint.

## Implemented behavior

- Optional in unprotected local development; API startup/readiness require it in
  staging and production. **Migration 0020** adds a stream binding. Explicit offline
  binding on the current source bootstraps existing deletion tombstones. Protected
  DBs refuse startup without the matching journal, even in development. Replay
  refuses an unbound/pre-activation snapshot; never bind an old restored snapshot
  to pretend missing history is known. Linux/POSIX local filesystem only; Windows owners use Docker Desktop.
- An independently mounted journal records authenticated project/account deletion,
  logout/family revocation/reuse and password-change/reset intentions **before**
  their application DB transaction commits or HTTP success is acknowledged.
- Journal file is mode 0600 in a 0700 server-owned directory. No symlinks, junction
  indirection on the supported Linux host, hard links or public file permissions.
  User/project UUIDs and storage namespace identifiers are encrypted with existing
  Fernet; no email, IP, source path, password, code or credential is recorded.
  Stream UUID, sequence, preceding MAC and encrypted payload form an HMAC chain.
  This is integrity/encryption, not protection against a writer with the key.
- Local process flock serializes API processes; lock acquisition is bounded to five
  seconds. Append and initialization fsync before acknowledgement. A damaged,
  missing, full or unsafe journal makes security-changing requests fail with 503.
  There is **no automatic creation/reinitialization after loss**.
- Write-ahead records can survive a subsequently failed DB transaction/HTTP reply.
  Replay treats these as conservative deletion intentions. That may hide more
  data than the eventual live DB commit; privacy is favored over resurrection.
  Never promise every journal record means the user saw a successful response.
- Every replay revokes **all** restored access sessions, refresh families and
  email actions, cancels mail payloads/active work/dispatch, aborts incomplete
  uploads, and disables **every surviving restored password**. A new recovery
  proof is required. Replaying only recorded logouts would miss older compromised
  passwords/credentials; blanket invalidation is deliberate.
- Reapply account/project tombstones, including cleanup identities absent from the
  snapshot. Keep unrelated completed projects and their output hashes intact.
  Current/recorded remote namespaces are preserved; unknown/mismatched namespaces
  defer cleanup rather than claim erasure. Existing retryable cleanup owns media I/O.
- Replay first creates an independent access hold, then commits the DB transaction,
  then marks the hold applied. Crash/failure leaves access blocked. API middleware
  denies traffic while held (liveness /health remains available); readiness/startup
  also fail. This is a last guard, **not a substitute for stopped writers**.
- Explicit release requires the same current checkpoint, successful replay and a
  **120-second retirement interval**, longer than supported 60-second signed URLs.
  Old API/worker/mail/ingress processes must remain stopped; retire old signing/
  storage capabilities and fence old targets before cutover. Cleanup has a further
  conservative writer deadline; replay/release do not claim immediate erasure.

Migration **0020_restore_binding** is required. No new dependency, paid API,
outgoing mail, billing or AI added.

## Local Docker setup after review/merge

Finish pending uploads, stop writers and back up current PostgreSQL/media first.
Do not use `down -v`. From repo root:

```powershell
git pull --ff-only
docker compose stop api worker queue-supervisor mail-worker
docker compose -f compose.yaml -f compose.restore-journal.yaml build api worker queue-supervisor migrate mail-worker journal-init
docker compose -f compose.yaml -f compose.restore-journal.yaml --profile maintenance run --rm --no-deps journal-init
docker compose -f compose.yaml -f compose.restore-journal.yaml run --rm --no-deps api python -m app.migrate
docker compose -f compose.yaml -f compose.restore-journal.yaml run --rm --no-deps api python -m app.restore_replay --bind --offline
docker compose -f compose.yaml -f compose.restore-journal.yaml up -d
docker compose -f compose.yaml -f compose.restore-journal.yaml exec -T api python -m app.restore_replay --checkpoint
```

The create-only init service has no network, uses root only to own the empty
separate volume, drops to the application user, and writes a random private key
without printing it. It refuses an existing/nonempty volume. API is unprivileged
and keeps its existing sandbox/limits. Workers do not mount the journal or key.
No mail service is activated by the overlay.

Keep using **both Compose files** for this protected stack; omitting the overlay
on a bound database now refuses API startup/readiness rather than disabling protection. Do not remove/roll back the journal volume
when restoring PostgreSQL or media. The local demonstration key lives in that
independent volume, so it shares the volume's loss domain. Before real staging,
move key custody to an approved separately protected secret mount/vault and keep
current encrypted journal copies/checkpoints outside the snapshot failure domain.
The default Compose stack remains a development option, not staging acceptance.

Native Linux operators may set `RESTORE_JOURNAL_DIR` outside the media tree and
`RESTORE_JOURNAL_KEY_FILE` to a private existing Fernet key file, then explicitly
run `PYTHONPATH=apps/api python -m app.restore_replay --init`, migrate to 0020,
and explicitly `--bind --offline` against the current stopped source. Never paste keys into
chat/history/Git; prefer the Docker init for the local test. Do not change a key
in place: old journal records would become unreadable. Key rotation/multi-key
migration and immutable remote journaling remain deployment work.

## Restore procedure — isolated NEW target only

1. Fence external access and stop **all** API, decoder workers, queue supervisors,
   senders, upload/maintenance writers and old target access. Take a safety copy;
   verify encrypted backup manifest/config/version/key references. Never overwrite
   the only live DB/media copy. Snapshot encryption/offsite rotation is separate.
2. Preserve the **current** independent journal and key, including later security
   requests. Export a checkpoint **after source writers stop** and retain it in an
   independently trusted operator location, not the restored DB/media archive:

   ```powershell
   docker compose -f compose.yaml -f compose.restore-journal.yaml run --rm --no-deps api python -m app.restore_replay --checkpoint | Set-Content -Encoding UTF8 .data\restore-current-checkpoint.json
   ```

   Use the explicit encoding above on Windows PowerShell 5. Checkpoints contain
   only version/stream ID/count/head, no key or user data. Do not fabricate a
   checkpoint from an old restored stream.
3. Restore DB and media into an isolated new target, configure the **current**
   independently retained journal/key and compatible private namespaces, and run
   schema checks. The tool uses the configured DATABASE_URL; review that isolated
   target before proceeding. It never selects a production target for you.
4. Mount the trusted UTF-8 checkpoint read-only into the one-off API container at
   `/run/restore-checkpoint.json`. Against that isolated target, first preview:

   ```text
   python -m app.restore_replay --replay --expected-checkpoint /run/restore-checkpoint.json
   ```

   Preview verifies full chain plus exact expected stream/head/count, prints coarse
   counts and changes no DB/media. Missing/corrupt/rolled-back stream or checkpoint
   mismatch refuses. File hashes alone cannot establish freshness or provenance.
5. Apply while all writers remain stopped:

   ```text
   python -m app.restore_replay --replay --expected-checkpoint /run/restore-checkpoint.json --apply --offline
   ```

   `--offline` is an operator acknowledgement, not automatic proof other hosts are
   stopped. The hold guards this API configuration; it cannot fence an old host
   configured without the journal. Interrupted replay keeps the hold. A rerun
   against the same stopped target/checkpoint is conservative/idempotent; do not
   rerun against a reopened target after users recover credentials.
6. Verify private replay report, expected tombstones, ownership, namespace and
   cleanup deadlines. Wait at least 120 seconds. Release explicitly:

   ```text
   python -m app.restore_replay --release --expected-checkpoint /run/restore-checkpoint.json --offline
   ```

   Restart protected services only after host/network/quotas/cleanup checks. All
   sessions require fresh recovery. Use an approved newly issued real email proof;
   local file proofs are test-only and forbidden in staging/production. If delivery
   is unavailable, accounts stay locked; there is no password-reset bypass. Deleted
   accounts stay disabled; old deletion receipt capabilities are not reconstructed.
7. Verify fresh survivor recovery, owner-only known download and new render,
   monitoring, and eventual local/S3 cleanup before approving target cutover.
   Resume periodic current checkpoint/journal protection and preserve the old
   target read-only under the approved retention policy.

If a tail write/fsync fails or a stream is damaged, preserve all files and the
independent checkpoint; stop security writers and investigate. Do not truncate,
reinitialize, delete a hold or clear a key to make readiness green. A stranded
create-only temporary hold file after process death also requires offline review.

## Automated acceptance and scope

```bash
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/test_restore_journal.py -q
.venv/bin/python scripts/smoke_restore_journal.py
.venv/bin/python scripts/smoke_restore_journal.py --postgres
```

The smoke accepts **no existing target**. PostgreSQL mode owns its own temporary
container and uses an existing `postgres:16-alpine` image with `--pull=never`;
SQLite is a disposable local fixture. Both snapshot before actual HTTP deletion/
password/logout requests, keep the independent journal current, restore into a
new already-bound DB snapshot, replay, reject old access/refresh/passwords, recover one survivor through
a new local-only proof, compare surviving output SHA-256, and verify deleted-media
cleanup. No email/provider call. Tests advance only stopped disposable fixture
release/cleanup deadlines; the production CLI has no time bypass.

Private synthetic reports/logs are ignored under `.data/restore-journal-*`; temporary
DB/media/key/journal and owned PG container are removed. The Docker create-only init did run successfully with current source/current
cryptography copied into a disposable volume on the older validation image. The
final unprivileged-readiness/reinitialization container check and complete rebuilt
overlay activation could not finish because the managed Docker VFS disk filled.
Those host checks are **pending**, not passed; native journal permission/refusal
regressions passed. No production image rebuild or containment acceptance is claimed.

Still open: encrypted offsite backup/rotation and loss recovery, independent
immutable current checkpoint/journal storage, approved key custody/rotation,
actual production target fencing/restore exercise, complete remote versioned/
late-write erasure and legal retention. The local journal is bounded to 64 MiB/
100,000 records (including genesis); it refuses further writes at the bound.
Replay/append validate the full stream: large-history performance and safe archival
need separate work before scale. No production DR SLA or full privacy erasure claim.
