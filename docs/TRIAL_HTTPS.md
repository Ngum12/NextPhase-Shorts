# IP-restricted domain HTTPS for the disposable VPS trial

Prerequisite: successful `vps_trial.py accept --synthetic` on the actual host.
This optional separate Compose project adds trusted domain TLS and allows API
requests only from one direct client public IP. Exact GET/HEAD `/backup-info` and
`/backup-privacy` paths serve public static OAuth information; they never proxy to
the API. See BACKUP_GOOGLE_OAUTH.md. It retains the existing private
edge, operator channel, DB/media, journal and credentials. It does not migrate
data or establish public release readiness. No email, billing or AI is enabled.

Use a domain whose A record points directly at the VPS; do not enable a CDN/proxy
or add an AAAA record for this IPv4-only listener. Requests from all other IPs get
403 outside those two information paths, even with a forged forwarding header. Phones must share the allowed public
IPv4 (turn off cellular fallback); dynamic IP changes require a reviewed update.
This is a network access restriction, not a substitute for app authentication.

From the VPS checkout, create the dedicated settings without overwriting files:

```bash
umask 077
test ! -e .data/trial-https.env && printf '%s\n' \
  'TRIAL_DOMAIN=shorts-api.techskillnow.com' \
  'TRIAL_CLIENT_IP=105.179.8.146' > .data/trial-https.env
ht() {
  env -u TRIAL_DOMAIN -u TRIAL_CLIENT_IP -u COMPOSE_PROFILES \
    -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
    -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock compose \
    --project-name nextphase-trial-https --env-file .data/trial-https.env \
    -f compose.trial-https.yaml "$@"
}
ht config --quiet
ht run --rm --no-deps certificate-init
ht run --rm --no-deps public-edge validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Only proceed when validation succeeds. Caddy uses ACME HTTP/TLS challenges:
inbound TCP 80 and 443 must be reachable for certificate issuance/renewal.
Allow these in the provider firewall if configured, and in UFW:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
ht up -d public-edge
```

Docker publishes can bypass UFW; the Caddy direct-peer allowlist is mandatory.
Port 80 serves ACME challenges and otherwise returns 404, not the API. Port 443 applies
the IP restriction to application requests. Certificates/ACME keys persist in
the private `nextphase-trial-https_trial-certificates` volume; retain it through
updates/restarts. Do not print its private keys or disable certificate checking.
Public certificate issuance discloses the hostname in certificate transparency.

From the allowed personal connection (Windows PowerShell):

```powershell
curl.exe --fail --show-error https://shorts-api.techskillnow.com/ready
curl.exe --silent --output NUL --write-out "%{http_code}" https://shorts-api.techskillnow.com/api/v1/jobs
```

Expect verified TLS with readiness JSON and 401 for unauthenticated jobs. From
a second permitted personal connection whose public IP differs, expect 403.
Do not test by bypassing workplace filtering. Use synthetic media only; do not
invite customers or migrate existing accounts. Existing private acceptance does
not exercise this front door: mobile upload/render/Save still needs direct proof.

If issuance/startup fails, retain volumes and inspect `ht logs --tail 50 public-edge`
privately (ACME diagnostics can contain account details). Never repeatedly delete
ACME state to retry: CA limits apply. Stop only this front door with
`ht stop public-edge`; the private trial remains running. Remove UFW allowances
if no other service needs them. `ht down` without `-v` retains certificate state.

Local validation: `python scripts/smoke_trial_https.py --caddy /path/to/caddy`.
This tests real routing/denial/header handling and configuration adaptation,
without contacting a CA or claiming real domain issuance/phone acceptance.
