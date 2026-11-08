# Phase 2 package 2 — real email verification and recovery

Preparation started after the owner reported all package 1 Pixel checks passed.
This document is a work checklist, not a claim that real delivery is implemented.
The fixed six-package checklist remains authoritative; no later package is skipped.

## Existing baseline

Migration 0014 provides one-use expiring proofs, credential binding, action
invalidation and private local-file delivery. Reset revokes all sessions and
refresh families. Mobile currently distinguishes disabled and local test delivery.
Local proof is deliberately not real-world email ownership; do not promote old
`local_file` verification records into trusted production email verification.

## Deliver together in one package review

1. Add a provider transport behind explicit disabled-by-default configuration;
   require TLS/certificate verification, bounded timeouts and no user-controlled
   destination host/credentials. Preserve the development-only local adapter.
2. Commit a durable encrypted delivery outbox with action issuance. Separate
   encryption keys from JWT/session keys; no raw proof/recipient in logs or error
   responses. Design key rotation, expiry and cleanup before activation.
3. Lease/fence bounded dispatch work; retry transient failures with backoff and
   explicit terminal states, recover process crashes and clean expired payloads.
   SMTP/provider acceptance does not prove inbox delivery; duplicate delivery may
   occur after an ambiguous send unless provider idempotency is available.
4. Serialize issuance/redemption with account deletion/password changes and stop
   stale queued proofs. Define in-flight-send limits honestly: a message already
   accepted by a provider cannot be recalled by a DB revocation.
5. Define verified-channel policy and enforce it server-side at the selected
   protected actions. Leave sign-in/recovery/account deletion reachable so existing
   unverified accounts are not stranded. Only proofs delivered through the approved
   real channel can establish production email verification.
6. Update mobile capability handling and copy for disabled/local/real delivery;
   preserve generic account-enumeration responses, originating-session guards,
   existing upload state and safe retry behavior.
7. Test delivery failure/restart/duplicate-send/expiry/deletion races on SQLite and
   PostgreSQL; add a disposable local transport proof, run automated regressions
   and Android export. Request one focused real-inbox Pixel check only once the
   sender is configured and activation is authorized.

## Configuration and activation gates

Need provider and sender-domain names first. Secrets belong in server/environment
secret storage, never chat, git, `EXPO_PUBLIC_*`, sample commands or logs. A sender
domain must be controlled and authenticated per provider policy; document SPF/DKIM/
DMARC, quotas, retention/privacy, terms and costs for the selected provider.

Implementation and local sink tests can proceed without sending external messages.
Before any real-send activation, present concrete configuration/test recipients and
cost limits for the required owner approval. Do not create paid accounts/resources,
send real email, or treat a local sink as real-inbox acceptance. Package 2 stays
open until its real-channel, policy, review/CI and focused-device gates are met.
