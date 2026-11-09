# One consolidated Phase 2 build and acceptance report

This release combines **encrypted backup/recovery, private TLS rehearsal,
operational delivery/cost controls, and final evidence review** into one branch,
one automated acceptance command and one Windows Docker activation script. It
adds no application migration after 0020 and changes no mobile dependency/source.
No repeated phone/full regression sequence is needed from the owner.

This is a **private local rehearsal**, not a public/cloud production approval.
Actual hosting/budget, provider billing records, IAM/secret custody and legal
approvals cannot be manufactured by passing local tests. The report keeps them
false until supplied. No paid resource, DNS change, mail, AI or billing activated.

## 1. Encrypted backup and safe recovery

`app.backup_bundle` streams an authenticated container in bounded 1-MiB chunks
using existing Fernet cryptography. Each frame authenticates archive identity,
sequence/type and content. Final authenticated SHA-256 plus exact EOF prevents
truncation/reordering/splicing/appending; file inventory hashes are also checked.
This is a versioned backup container using standard encryption, not new cipher
primitives or a claim of cryptographic certification.

The create command requires an explicit stopped-writer acknowledgement and exact
current journal checkpoint. It includes an existing PostgreSQL custom dump or
SQLite snapshot, the selected **local media directory**, encrypted snapshot
journal and manifest. No journal/backup/CA key is included. Create-only outputs,
private permissions, no links/hardlinks, change detection and failure cleanup
preserve inputs. Encryption key generation never prints the key.

Restore authenticates before parsing the archive, uses a new private target only,
checks file/count/size/hash bounds and rejects paths, links, devices, duplicate
names and unexpected members. It never calls tar extraction helpers, restores a
DB, overwrites a current journal or deploys media. Partial failures remove only
its exclusively created target. Low disk aborts before exhausting the volume.

**The journal inside the bundle is a snapshot, not the current restore authority.**
Supply the independently retained CURRENT journal/key/checkpoint to the protected
0020 replay/release procedure. Pre-activation snapshots remain refused. Existing
post-snapshot deletions and credential invalidation are tested after decryption.
Do not replay against the live database as an upgrade test.

CLI (Linux/offline maintenance; paths are placeholders, not real secret values):

```text
python -m app.backup_bundle keygen --key-file /separate/private/backup.key
python -m app.backup_bundle create --key-file /separate/private/backup.key --database-dump /input/database.dump --media /input/media --checkpoint /input/current-checkpoint.json --output /backups/new.npb --offline
python -m app.backup_bundle restore --key-file /separate/private/backup.key --bundle /backups/new.npb --output /isolated/new-target
```

The default authenticated-plaintext bound is 100 GiB; copies may require temporary
space roughly twice the archive size. Local/Windows file permissions need approved
current-user ACLs. **Remote S3 objects, versions, provider state and operational
volumes are not copied by the local-media bundle.** Configure provider-native
private backups/versioning/export and namespace-safe recovery after that provider
is approved. Prior plaintext safety snapshots remain private and require an
approved retention/cleanup policy; this does not retroactively encrypt all copies.

## 2. Private HTTPS rehearsal

`compose.private-staging.yaml` layers over base + restore-journal Compose files.
Pinned official Caddy **2.11.9** serves API TLS on **127.0.0.1:8443**, with private
operator TLS only on the internal network. Admin/automatic public issuance are
off. Body/header/time bounds, private route denial, no-store/security headers,
forwarding-header removal and disabled raw request/access error logs are tested.
API still uses `--no-proxy-headers`; socket-peer rate limits remain conservative
behind one proxy. Real public proxy/client-IP/WAF policy needs separate review.

`staging-init` has no network, creates new private role volumes once, drops root
to app user, and never overwrites existing credentials. A 30-day localhost/edge
certificate is signed by a 365-day private CA. **CA signing and backup keys stay
in an offline-only volume**; runtime edge/agent/receiver get only their own files.
Existing initialized credentials are checked rather than regenerated.

This CA is not publicly trusted. Tests explicitly trust its public certificate
and prove that an untrusted client rejects it; **no verification is disabled**.
No phone/system trust-store installation is performed. The existing USB Expo Go
HTTP loopback preview remains unchanged; a publicly trusted approved certificate/
domain or a reviewed mobile trust configuration is needed for actual hosted
mobile HTTPS acceptance. Never add `verify=False` or bypass Android trust errors.

Existing host CPU/memory/PID/sandbox/storage limits remain. No private S3/cloud
IAM/network deployment is inferred from local volumes/networks. This profile is
not labeled APP_ENV=staging; actual staging also requires PostgreSQL/private cloud
storage, verified queue TLS and externally reviewed secrets/quotas/egress.

## 3. Operational delivery and cost controls

A private, token-authenticated local receiver accepts **only the fixed NextPhase
OTLP JSON envelope and coarse alert codes**, not arbitrary telemetry/PII. It keeps
bounded private SQLite records (20 MiB/10,000 deliveries; seven-day retention),
rejects unknown content/auth, and deduplicates identical delivery IDs. This is a
local archive/receipt sink, **not** a production OpenTelemetry collector/dashboard
or human notification channel. Overlapping OTLP batches can contain the same span;
do not sum batch counts as unique usage. Full collector storage/alert routing to
approved humans is still a deployment decision.

The operator agent polls every 60 seconds, verifies TLS with the private CA,
refuses redirects/unapproved destinations and requires explicit acknowledgements.
It sends traces and coarse statuses only, never the full secrets/cost snapshot.
Receiver token is role-separated. The agent has no customer-media mount or
direct external network: it reaches the DB/edge only on the internal operator
network. It explicitly reports media-disk monitoring as not observed by that role;
API/worker disk guards remain authoritative, and approved host disk monitoring
is still needed before deployment. The agent gets no API JWT/provider/mail secret;
a separate random local config key satisfies shared settings. Its DB connection
requests read-only transactions; actual database IAM remains a release gate.
Delivery failure is reported and retried on the next interval; watch that process
with approved operator tooling. No email/Slack/pager message was sent.

`app.budget_control` imports a trusted operator policy + provider export, with
Decimal USD amounts, explicit period/freshness and all components: API, worker,
DB, queue, storage, egress, backup and observability. Missing/unapproved components
remain incomplete. This is **an import adapter**, not proof of a provider invoice.
Source hash records which export was used. Estimates are not relabeled actuals.

```text
python -m app.budget_control --policy /private/policy.json --usage /private/provider-export.json --state /private/budget-state.json
```

Policy shape is in `deploy/private-staging/budget-policy.example.json` and stays
**unapproved**. Usage shape: `version:1,currency:"USD",mode:"provider_export"`,
ISO timezone-aware `window_start/window_end/updated_at`, plus `components` containing
each component name above with nonnegative USD decimal strings. Provider exports
older than 24 hours are refused. Mount the mode-0600 state from a private Linux volume read-only into API and
workers and set `BUDGET_STATE_FILE` only after approved input/scheduling exists.
Staging/production refuse a missing budget-state configuration; local development
can leave it disabled.
Refresh at least every five minutes; stale/missing/malformed configured state
pauses new admissions and worker claims. An exhausted budget stays paused until
explicit operator `--resume`; healthy import alone cannot silently reopen it.
Recovery, deletion, reads and existing accepted upload completion stay accessible.
Already running attempts finish within their existing limits.

The local rehearsal uses clearly marked synthetic `local_fixture` costs, rejected
in staging/production. The default local Compose stack has **no paid provider
budget state enabled**. This gate cannot stop idle infrastructure charges, existing
provider work, unreported requests or provider billing. Actual quotas/billing caps
and reconciliation must be approved and tested with the selected provider.

## 4. Final review is explicit

`release_review` combines automated results with the fixed external gate list in
`deploy/private-staging/release-evidence.example.json`. Default approvals are null.
The consolidated report can correctly say all local software checks passed while
`release_ready:false`. Operator attestations require an evidence hash/date, are
not independently verified legal signatures, and do not authorize spending.

Caddy official archive SHA-512 checksums and Apache-2.0 LICENSE are preserved.
The Docker image is pinned by manifest digest. No reference-kit assets or other
application dependencies were added. Full native/image/transitive source/codec/
font licensing, vulnerability review, controller identity/privacy terms and
provider policy approvals remain real release gates. No automatic risk waiver.

## One automated engineering acceptance command

On Linux/CI, with project Python dependencies/FFmpeg and a Docker-free native TLS
fixture (Caddy is downloaded from the pinned official release and checksum-verified):

```bash
.venv/bin/python scripts/consolidated_acceptance.py
# Reuse an already verified binary if supplied by approved operator tooling:
.venv/bin/python scripts/consolidated_acceptance.py --caddy /path/to/caddy
```

This runs the full SQLite backend suite, encrypted snapshot-before-deletion
restore/replay, and actual Caddy TLS upload/render/download, body/private-route/
forwarded-IP/log redaction checks, OTLP receipt, worker-failure alert and budget
admission-stop checks. It produces one ignored private report and logs under
`.data/consolidated-acceptance-*`. Report includes source commit, dirty-tree flag
and software-tree hash. No existing target or customer media is used.

CI separately runs full PostgreSQL tests and an encrypted pg_dump/new-DB pg_restore
drill. For resource-limited cloud validation only, `smoke_restore_journal.py
--encrypted-backup --test-postgres-container NAME` requires local `_test` DB
authority in `NEXTPHASE_TEST_DATABASE_URL`; it creates/drops fresh UUID databases
on that local test service and never restores an existing database. The ordinary
`--postgres` option owns its own disposable container.

## One Windows Docker activation after review/merge

Finish uploads first, keep real email/billing/AI off, then:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull --ff-only
powershell -ExecutionPolicy Bypass -File scripts\activate_private_staging.ps1
```

The script stops writers, privately backs up current PostgreSQL/local media,
builds updated roles, checks/creates private PKI once, exports an independent
checkpoint, encrypts the local bundle, authenticates/read-backs into a new target,
removes only that temporary verified copy, starts the protected stack and checks
TLS readiness/acknowledged operator delivery and captures the actual rebuilt worker
package inventory for review. Inventory is not a vulnerability/legal scan. Any native
command failure stops it.
It does not restore the live DB, change passwords, publish ports, alter DNS or
activate mail. Existing source/backup/key volumes stay intact. Never use `down -v`.

Keep all **three** Compose files for future starts. The encrypted bundle and
original safety snapshot remain private; no backup/key should be pasted into chat.
The script's Windows Docker execution is the **one remaining owner host check**;
local native tests do not claim that execution. The managed cloud Docker VFS disk
cannot support a rebuilt full container stack, so no such cloud pass is invented.
The offline volume is still on the same machine; independently protected key/
current-journal custody and an approved offsite destination remain required.
