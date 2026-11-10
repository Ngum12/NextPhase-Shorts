# VPS preparation and one private acceptance run

This is a **disposable, SSH-accessed development trial on a VPS**, before customer
data migration. It is not public staging/production acceptance. Use a fresh Linux
clone and the dedicated project below; do not run preparation on the working PC.
No purchase, provisioning, DNS changes, paid API or real email is performed by
these tools. Contabo is the owner's shortlisted provider, not a code dependency.

## What is already accepted

The owner supplied successful Windows activation of the consolidated build after
merging main `fe22703`: PostgreSQL/local-media snapshot, encrypted 13-file bundle
and authenticated readback, role-separated private PKI, healthy services, verified
HTTPS readiness and acknowledged operator delivery. The actual rebuilt worker
inventory was captured (292 OS / 47 Python packages). These are owner-reported
results, not a cloud-executed Windows test or completed vulnerability/license scan.
Do not repeat that activation or the old phone suite just for this preparation.

## 1. Establish access to the new host

When provisioned, use Ubuntu 24.04 LTS x86-64 if offered. Verify the SSH host-key
fingerprint using the provider's independent console before accepting it. Create
a normal administrator with an SSH key; test a second session before disabling
password/root SSH login. Keep recovery-console access. Docker group access is
effectively root access; restrict it to trusted administrators.

Install Docker Engine and Compose from official Ubuntu/Docker instructions
(https://docs.docker.com/engine/install/ubuntu/). Require Compose **2.24.4+** for
the explicit override/reset tags. Install Git, Python 3.12 with venv and FFmpeg.
Keep OS/security updates current. Do not use an unreviewed installer script or
disable the application's worker containment when a host check fails.

For the private trial, expose **only SSH**, restricted to your administrator IP
where practical, using the provider firewall. Do not publish 8000/18000, 8443/
18443, PostgreSQL, Valkey, collector or Docker socket. Docker publishing can bypass
ordinary UFW assumptions; this profile also binds its only ports to loopback.
Do not lock out SSH while changing firewall rules. Public 80/443 are a later,
explicit trusted-HTTPS deployment, not needed for this trial.

Confirm the provider permits sustained FFmpeg CPU processing, billing/cancellation
terms and traffic limits. The planning target is 4 vCPU/8 GB RAM/100–160 GB SSD,
one render at a time; that is not measured production capacity or an SLA.

## 2. Prepare the isolated trial

On the **new VPS**, in a fresh checkout of the reviewed main branch:

```bash
git clone https://github.com/Ngum12/NextPhase-Shorts.git
cd NextPhase-Shorts
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements-dev.txt
.venv/bin/python scripts/vps_trial.py prepare
```

`prepare` creates only `.data/vps-trial/` (0700): fresh database, session and broker
credentials, private env files (0600) and broker configuration. It refuses an
existing or partial destination; never delete/reinitialize it to fix a login.
It starts no services and prints no credentials. Config values are available to
trusted Docker administrators through inspection; this is not a vault/IAM setup.
Do not print or publish `docker compose config`, inspect output or env files.

Define this convenience function **in the VPS Bash terminal**. Always use all
four files, the dedicated env file and project name. This is not the Windows
Compose command and must not be mixed with the PC's project/volumes.

```bash
dc() {
  env -u VPS_DATABASE_URL -u VPS_DB_PASSWORD -u COMPOSE_PROFILES \
    -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
    -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock compose --project-name nextphase-vps-trial \
    --env-file .data/vps-trial/compose.env \
    -f compose.yaml -f compose.restore-journal.yaml \
    -f compose.private-staging.yaml -f compose.vps-trial.yaml "$@"
}
.venv/bin/python scripts/vps_trial.py check
```

The resolved configuration is checked in memory: new credentials, one render,
required sandbox/CPU/RAM/PID controls, private ports and dedicated volume names.
The trial uses local media and `APP_ENV=development` honestly. It has no claim to
production S3 privacy, broker TLS, verified email or provider spend caps. It sets
a conservative 20-GiB logical media budget and 5-GiB free-space floor; monitor the
host separately because backups, images and PostgreSQL also consume disk.

## 3. First initialization — fresh disposable volumes only

The following deliberately starts a **new empty test installation**. It does not
restore accounts or footage. Each command must succeed before continuing:

```bash
dc build api worker migrate queue-supervisor operator-agent operator-receiver staging-init journal-init backup-tool
dc run --rm --no-deps worker python -m app.worker_hostcheck
# STOP if ready is false. Never turn the required protections off.
dc up -d --wait db queue
dc run --rm migrate
dc run --rm --no-deps journal-init
dc run --rm --no-deps api python -m app.restore_replay --bind --offline
dc run --rm --no-deps staging-init
dc up -d --wait api worker queue-supervisor operator-receiver edge operator-agent
```

Initializers are create-only; do not repeat them after a partial failure. Inspect
the failed step privately and retain its credentials/volumes. For an already
initialized trial, use only the final `up` command. No `--scale worker` is needed;
database admission also permits at most one render.

## 4. One acceptance entry point

```bash
.venv/bin/python scripts/vps_trial.py accept --synthetic
```

This inspects configuration, checks containment inside the actual worker, verifies
private edge TLS, evaluates monitoring and obtains an operator delivery receipt.
Only after those succeed it runs the existing HTTP synthetic account/resumable
upload/queue/render/download/owner-isolation smoke against **127.0.0.1:18000**.
It never restarts the target, restores databases, enables email, alters the host
firewall or runs replay against the live account database. Without `--synthetic`
it checks health only and reports that workflow acceptance was not exercised.

The JSON report is create-only/private under `.data/vps-trial/acceptance-*.json`;
command errors are reduced to a fixed failure code, not raw diagnostics. Earlier
passing keys show how far it got. Synthetic smoke evidence remains in the ignored
`.data/smoke-*` directory. Test accounts/media/metadata can remain; this is why the
target must be disposable. A short synthetic render is not a representative
load/soak, 60-second speed guarantee or AI benchmark. Reports always keep
`public_release_ready:false`.

For temporary Pixel preview, open a Windows PowerShell SSH tunnel (replace the
uppercase placeholders with the administrator and VPS address):

```powershell
ssh -N -L 127.0.0.1:8000:127.0.0.1:18000 ADMIN@SERVER_IP
```

Keep your working PC API stopped if it occupies 8000. Existing USB `adb reverse
tcp:8000 tcp:8000` plus the actual Metro port connects to this private tunnel.
This transports the loopback HTTP preview through encrypted SSH; it does **not**
test public mobile HTTPS. Private CA certificates are not installed on the phone
and certificate verification must never be bypassed.

## 5. Migration, fencing and rollback — separate from the disposable trial

Do not automatically migrate existing accounts into this trial. First accept its
host/performance results, select approved private S3/offsite destinations, approve
provider costs/quotas and arrange trusted mobile HTTPS and human alert routing.
Then prepare a separately reviewed hosted configuration with distinct secrets,
least-privilege DB/storage credentials, queue TLS and the real budget-state feed.
The local trial profile must not be renamed production to bypass these gates.

At the migration window:

1. Finish or explicitly cancel active uploads/renders. Block new ingress and stop
   **all** source writers, including API, worker, supervisor and mail dispatcher.
   Keep the current independent journal intact; export its checkpoint **after**
   writers stop. Record the code/image/schema versions and storage namespaces.
2. Follow [encrypted backup](CONSOLIDATED_ACCEPTANCE.md) for a consistent PG custom
   dump and local-media bundle. Keep the encryption key separately. Copy the
   independently current journal/key/checkpoint separately using authenticated
   transfer to approved private destinations. The archived journal is not current
   restore authority. S3 originals/versions/provider state are **not** in that bundle.
3. Authenticate/read back into a **new isolated target**, compare manifest hashes
   and prove independent key availability. Restore only into new DB/media targets;
   never overlay a live database or transplant the disposable trial's journal.
   Use [protected replay/release](RESTORE_JOURNAL.md) with the independently current
   stream. This invalidates old credentials/passwords; approved recovery delivery
   must be available before users are invited back. Do not enable it accidentally.
4. Fence the old host before releasing the new one: remove its ingress and revoke
   its provider capabilities as applicable. Never allow both installations to
   accept writes. Complete HTTPS, ownership, resume/render/Save, deletion,
   monitoring/alerts and restore acceptance on the actual hosted configuration.
5. If acceptance fails **before new writes**, leave the new target held and resume
   the unchanged source only after confirming it is the sole writer. **After new
   writes**, do not switch back to the old snapshot: it lacks new data and security
   intentions. Fence the new host and use the latest DB/media/current-journal
   state through the protected recovery procedure. DNS rollback alone is unsafe.

Retain the PC and verified backups until migration and recovery are proven. Never
use `down -v`, volume deletion or journal reinitialization as an upgrade/rollback.
Offsite copies/current-checkpoint freshness, recovery objectives, remote object
erasure, privacy/licensing/provider review and actual costs remain external gates.
No public release or Phase 3 acceptance is implied by this preparation.
