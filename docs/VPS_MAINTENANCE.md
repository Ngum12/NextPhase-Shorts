# Scheduled private VPS maintenance

For the already initialized, accepted `nextphase-vps-trial` installation only.
This adds no cloud resources, public endpoints, schema changes or paid services.
Run as the normal trusted Docker administrator, **not root**. Docker access is
administrator-equivalent. The script selects the documented four-file project
itself; no interactive `dc`/`ht` function is needed after reconnecting.

## What it does

- Nightly backup at **04:00 Africa/Kigali** (02:00 UTC). Checks free space and
  queues before stopping writers. Busy queues defer the backup and report failure;
  a second check after stopping catches new submissions. A race can interrupt a
  newly started render, which remains subject to existing lease/retry recovery.
- Stops only writers observed running, makes a PostgreSQL custom dump and matching
  checkpoint, creates an encrypted local-media bundle and authenticates/decrypts a
  readback into a fresh target. Removes only that new plaintext verification copy.
- Copies encrypted output to an administrator-readable mode-0600 file, compares
  its SHA-256 and resumes the previously running services. Does not start an
  inactive mail worker. A saved pause marker and systemd recovery hook retry
  writer restart after failure/interruption. SIGKILL/host loss still needs operator
  recovery; check status after an outage. It never restores the live database.
- Checks local readiness, worker/queue monitoring, 5-GiB disk warning, verified
  domain certificate validity (14-day warning), and backup freshness (30 hours)
  every five minutes. Expected backup pauses are reported as maintenance rather
  than API/worker outages. HTTPS is checked directly on loopback with the real
  domain SNI and trusted CA validation, independent of the client-IP allowlist.
- Optional separate Resend email for coarse failure/recovery status. Repeated
  unchanged failures are limited to one message/hour/topic. No account email,
  authentication policy, AI, billing or customer-content sending is enabled.

Backups stay on the VPS until copied offsite. **A timer is not an offsite backup.**
The saved vault key can decrypt these bundles; the security journal key is not
included. A bundle's journal is a snapshot, not automatically current authority
for later deletions/revocations. Keep independently current journal/checkpoints
protected outside the VPS and follow RESTORE_JOURNAL.md before any recovery.

No automatic retention/deletion is configured. Both original container-owned
ciphertext and an operator-readable copy are retained. Failed private inputs are
retained for diagnosis; successful inputs are removed. Required free space is
at least 10 GiB plus four times measured media/database size before starting;
the backup library also checks space during creation/readback. Plan capacity
and reviewed retention/offsite policy as usage grows. Never use `down -v`.

## First manual validation on the VPS

Finish uploads/renders; the backup briefly pauses the app. From the VPS checkout:

```bash
sudo apt-get install -y acl
.venv/bin/python scripts/vps_maintenance.py backup
.venv/bin/python scripts/vps_maintenance.py status
```

Require `ok:true`, `authenticated_readback:true`, a SHA-256 and resumed services.
`offsite_copy:false` is explicit. Output files are under `.data/scheduled-backups/`.
The script grants the detected container UID access only to its required bind
mount directories/new inputs using ACLs; it does not use world permissions or
assume the administrator and container share a UID.

## Secure, separate failure email

Use an existing Resend account with a verified sender domain and a dedicated
**sending-only** key restricted to that domain where supported. Check provider
plan/limits; this script provisions nothing and cannot prevent provider charges.
Do not use a customer's address as sender or enable the app's auth-mail worker.
Example addresses below are placeholders; use the approved sender and recipient:

```bash
.venv/bin/python scripts/vps_maintenance.py email-setup \
  --sender monitor@YOUR_VERIFIED_DOMAIN --recipient YOUR_ALERT_ADDRESS
```

Type the key only at the hidden terminal prompt. Never paste it into chat or
command arguments. Settings/key stay mode 0600 under the administrator-owned
mode-0700 `.data/maintenance/`; do not commit, upload or print them. Setup refuses
existing files; changing a saved binding requires private operator review.

```bash
.venv/bin/python scripts/vps_maintenance.py email-test
```

Provider acceptance is not inbox delivery: confirm the test arrives in the actual
inbox/spam folder before relying on email. Tests use a simulated provider and
send nothing. A VPS outage or outbound failure prevents this VPS from emailing;
independent external uptime monitoring is still required for loss-of-host alerts.

## Generate, inspect and install the timers

After manual backup/readback and inbox validation, generate units as the normal
administrator. This captures the actual checkout path, Python venv and username:

```bash
.venv/bin/python scripts/vps_maintenance.py units
cat .data/maintenance/systemd/nextphase-backup.timer
cat .data/maintenance/systemd/nextphase-monitor.timer
sudo install -m 0644 .data/maintenance/systemd/nextphase-*.service /etc/systemd/system/
sudo install -m 0644 .data/maintenance/systemd/nextphase-*.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/nextphase-backup.service /etc/systemd/system/nextphase-backup.timer /etc/systemd/system/nextphase-monitor.service /etc/systemd/system/nextphase-monitor.timer
sudo systemctl daemon-reload
sudo systemctl enable --now nextphase-backup.timer nextphase-monitor.timer
sudo systemctl list-timers 'nextphase-*'
```

Existing generated units are preserved rather than overwritten. Timers are
persistent: missed runs may execute after boot/enabling. No schedule is installed
or activated by merely pulling code or generating files. No automatic Git pull,
package update, reboot, credential rotation or source rebuild is scheduled.

## Check and recover

```bash
.venv/bin/python scripts/vps_maintenance.py status
sudo systemctl status nextphase-backup.service nextphase-monitor.service --no-pager
sudo journalctl -u nextphase-backup.service -u nextphase-monitor.service -n 30 --no-pager
```

Status output contains coarse diagnostics, timestamps and encrypted backup names/
hashes, never secrets/customer content. Unit nonzero exits indicate failure or
attention required. Provider errors are sanitized; never dump a key to diagnose.
To retry a writer restart after an interrupted backup (refuses an active lock):

```bash
.venv/bin/python scripts/vps_maintenance.py resume
```

Stop future scheduled work without deleting existing files or services:

```bash
sudo systemctl disable --now nextphase-backup.timer nextphase-monitor.timer
```

Do not kill a running backup to disable its schedule; wait for completion and
check writer status. The existing private app/HTTPS stack remains separate.
