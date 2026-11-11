# Phase 2 evidence ledger — 11 November 2026

This consolidates evidence supplied during the owner-led Contabo setup. Private
trial acceptance and public production approval remain distinct. Earlier status
sections record what was known at their increment; this ledger updates them.

| Area | Actual private-VPS evidence supplied by owner | Remaining release condition |
|---|---|---|
| Host | Ubuntu 24.04, 4 CPUs, 8 GB RAM; unprivileged/cgroup/filesystem/network hostcheck ready | Representative long load/soak, exact artifact security/license acceptance |
| Access | Separate administrator, tested key-only SSH, root/password SSH disabled, UFW active | Recovery-access/key custody and ongoing operator review |
| API/phone | Trusted domain TLS; owner phone upload/render/Save/playback; jobs 401 and docs 404 | IP-restricted disposable trial; broader customer/network/device acceptance |
| Queue/isolation | Actual durable stack healthy; one-render capacity; strict worker checks passed | Production queue TLS, approved storage/IAM and capacity policy |
| Backup | Encrypted local-media bundle authenticated; new test PostgreSQL DB restored, migration 0020/23 tables, test DB removed | Full real-host protected security replay/fencing exercise and approved retention |
| Offsite | Actual systemd job generated fresh encrypted backup, uploaded Drive copy, downloaded/verified matching bytes; offsite status true | Drive is mutable, not immutable/offline custody; provider capacity and retention |
| Key/journal | Owner verified backup-key and journal/key/checkpoint attachments in encrypted KeePassXC vault and reports off-VPS vault copy | Journal snapshot is current only at export; independent immutable/current checkpoint custody remains open; rotation not supported and owner chose to leave key unchanged |
| Monitoring | Five-minute monitor succeeded; actual Resend inbox test; external Healthchecks failure/recovery mail test reported successful | Heartbeat is not an outside HTTP probe; representative alert/failure coverage and provider-policy acceptance |
| Schedule | Installed/verified systemd services/timers; 04:00 Rwanda nightly backups; successful manual systemd run | Future unattended runs/retention capacity still require observation |
| Cost/privacy/governance | Owner authorized/purchased this VPS and operator notifications | Actual approved provider spend/quotas/export feed, controller/privacy/terms/DPA/license/security signoffs |

The fixed checklist's external gates are **not marked complete**. The latest
owner instruction asks development to continue after seeing the next-milestone
plan. The isolated [analysis pilot](ANALYSIS_PILOT.md) is review-only preparation,
not deployment, public release, paid inference or a claim that Phase 2/3 is closed.
It adds no production endpoint, migration, worker activation or mobile feature.

Work still needed before rollout: representative speech/model acceptance and
isolated analysis-worker integration; approved production storage/queue TLS/IAM;
current-journal offsite freshness/immutable custody and real protected recovery;
real cost ceilings; representative capacity, security/image/license and owner
privacy/provider decisions. Do not repeat completed owner phone/server checks
solely because a historical note predates them.
