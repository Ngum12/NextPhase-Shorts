# Personal backup OAuth information pages

The owner's Google Auth Platform tooltip explicitly requires a valid app name,
support email, homepage and privacy-policy URL for external production status.
Non-sensitive `drive.file` permission does not remove this publishing requirement.
Leaving the URLs blank was incorrect for this console.

## Review and deploy

Review `deploy/backup-info/index.html` and `privacy.html`, including the public
support address, backup data, encryption, credential storage and manual retention.
These notices cover the personal backup connection, not the NextPhase Shorts
service's general privacy policy or a public-release/legal approval.

After merging, run in the VPS checkout:

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
ht() {
  env -u TRIAL_DOMAIN -u TRIAL_CLIENT_IP -u COMPOSE_PROFILES \
    -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
    -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS \
    -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock compose \
    --project-name nextphase-trial-https \
    --env-file .data/trial-https.env \
    -f compose.trial-https.yaml "$@"
}
ht config --quiet
ht run --rm --no-deps public-edge validate \
  --config /etc/caddy/Caddyfile --adapter caddyfile
```

After validation succeeds:

```bash
ht up -d --no-deps --force-recreate public-edge
```

This adds a read-only public-information mount. Database, worker, API and
certificate volumes are retained; do not remove volumes or reset credentials.
HTTP/80 stays 404 except for ACME. Only exact HTTPS GET/HEAD `/backup-info` and
`/backup-privacy` paths serve public HTML. They never proxy to an upstream.
Other methods, directories, unknown files and API paths retain direct-peer IP
restrictions. There are no scripts, forms, cookies, analytics or external assets.

Verify from Windows:

```powershell
curl.exe --fail --show-error https://shorts-api.techskillnow.com/backup-info
curl.exe --fail --show-error https://shorts-api.techskillnow.com/backup-privacy
curl.exe --fail --show-error https://shorts-api.techskillnow.com/ready
```

Both information pages must return HTML, also from an unapproved personal
connection. `/ready` is allowed only from the approved address and must remain
403 elsewhere. Do not change DNS, email records, TLS verification or API IP rules.

## Google fields after deployment verification

In **Branding**, set:

- App name: `NextPhase Backups`.
- Support/developer contact: the administrator's selected email.
- Homepage: `https://shorts-api.techskillnow.com/backup-info`.
- Privacy policy: `https://shorts-api.techskillnow.com/backup-privacy`.
- Authorized domain: `techskillnow.com`, the domain controlled by the owner.

Save, then use **Audience → Publish app**. Keep only the non-sensitive
`https://www.googleapis.com/auth/drive.file` scope and the Desktop OAuth client.
A domain entry is not ownership verification. If Google requests verification or
another requirement, complete that actual requirement; deployment does not
guarantee provider acceptance. Testing authorization can expire after seven days.
Publishing OAuth status does not publish the API or enable billing.

## Rclone connection remains separate

These pages do not change rclone credentials. Private client configuration, fresh
authorization and verified upload/readback with the dedicated client must follow.
Preserve the old remote while establishing a new one. Do not reuse a refresh token
bound to another client or paste secrets/token/client JSON into chat or Git.

`drive.file` is application-specific: the new client may not see the old client's
folder/files. Use a distinct dedicated folder, preserving older recovery copies.
Change maintenance's destination only after uploading and successfully reading
back a verified encrypted bundle. Automatic offsite protection remains unresolved
until that succeeds.
