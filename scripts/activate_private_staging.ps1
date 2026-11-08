# Existing local protected Docker stack only. No public hosting or paid service.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$composeArgs = @('-f','compose.yaml','-f','compose.restore-journal.yaml','-f','compose.private-staging.yaml')
function Invoke-NextPhaseCompose {
    & docker compose @composeArgs @args
    if ($LASTEXITCODE -ne 0) { throw 'Docker step failed. Stop here and share only the error; do not remove volumes or keys.' }
}
Write-Host 'Finish pending uploads first. Backing up the existing local protected stack.'
Invoke-NextPhaseCompose stop api worker queue-supervisor mail-worker operator-agent
$stamp = "$(Get-Date -Format yyyyMMdd-HHmmss)-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$backup = ".data\before-private-staging-$stamp"
New-Item -ItemType Directory -Path $backup | Out-Null
Invoke-NextPhaseCompose exec -T db pg_dump -U nextphase -d nextphase -Fc -f /tmp/nextphase-before-private-staging.dump
Invoke-NextPhaseCompose cp db:/tmp/nextphase-before-private-staging.dump "$backup\database.dump"
Invoke-NextPhaseCompose cp api:/var/nextphase/media "$backup\media"
New-Item -ItemType Directory -Force .data\staging-input,.data\encrypted-backups | Out-Null
Invoke-NextPhaseCompose build api worker queue-supervisor migrate operator-receiver operator-agent staging-init backup-tool
& docker compose @composeArgs --profile maintenance run --rm --no-deps staging-init -m app.staging_setup --check
if ($LASTEXITCODE -ne 0) {
    Invoke-NextPhaseCompose --profile maintenance run --rm --no-deps staging-init
}
# The backup tool has no network and mounts database/media input read-only.
Copy-Item "$backup\database.dump" .data\staging-input\database.dump -Force
$checkpoint = & docker compose @composeArgs --profile maintenance run --rm --no-deps backup-tool -m app.restore_replay --checkpoint
if ($LASTEXITCODE -ne 0) { throw 'Checkpoint export failed; services remain stopped.' }
$checkpoint | Set-Content -Encoding UTF8 .data\staging-input\current-checkpoint.json
New-Item -ItemType Directory -Force .data\journal-checkpoints | Out-Null
Copy-Item .data\staging-input\current-checkpoint.json ".data\journal-checkpoints\$stamp.json"
Invoke-NextPhaseCompose --profile maintenance run --rm --no-deps backup-tool -m app.backup_bundle create --key-file /var/nextphase/staging-offline/backup.key --database-dump /input/database.dump --media /source/media --checkpoint /input/current-checkpoint.json --output "/backups/$stamp.npb" --offline
Invoke-NextPhaseCompose --profile maintenance run --rm --no-deps backup-tool -m app.backup_bundle restore --key-file /var/nextphase/staging-offline/backup.key --bundle "/backups/$stamp.npb" --output "/backups/verify-$stamp"
# Only remove the new authenticated read-back copy; preserve encrypted/original snapshots.
$ready = Get-Content ".data\encrypted-backups\verify-$stamp\READY.json" -Raw | ConvertFrom-Json
if ($ready.authenticated -ne $true) { throw 'Read-back verification did not complete.' }
Remove-Item -LiteralPath ".data\encrypted-backups\verify-$stamp" -Recurse -Force
Invoke-NextPhaseCompose up -d --wait --wait-timeout 120 db queue migrate api worker queue-supervisor edge operator-receiver operator-agent
Invoke-NextPhaseCompose exec -T operator-agent python -m app.staging_check
Invoke-NextPhaseCompose exec -T operator-agent python -m app.operator_agent --url https://edge:9443 --ca-file /var/nextphase/staging-agent/root.crt --once
# Capture the actual rebuilt worker package inventory for the final review.
$inventoryDir = ".data\staging-review-$stamp"
New-Item -ItemType Directory -Path $inventoryDir | Out-Null
$imageId = & docker compose @composeArgs images -q worker
if ($LASTEXITCODE -ne 0) { throw 'Worker image identity lookup failed.' }
$workerImage = @($imageId)[0].Trim()
& .\.venv\Scripts\python.exe scripts\image_inventory.py --image $workerImage --output "$inventoryDir\worker-inventory.json"
if ($LASTEXITCODE -ne 0) { throw 'Image inventory failed; do not claim the final image review complete.' }
Write-Host 'Encrypted local-media bundle/read-back, private local TLS and operator delivery passed. Existing USB mobile URL stays unchanged.'
Write-Host 'This is local rehearsal; hosted deployment, real cost evidence and legal approvals remain separate gates.'
Write-Host 'Keep the offline key volume and current journal/checkpoints separate from backup rollback. Offsite custody still needs an approved destination.'
Write-Host 'The original private plaintext safety snapshot is retained; remote S3 objects are outside this local-media bundle.'
