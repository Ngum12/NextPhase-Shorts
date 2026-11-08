# NextPhase Shorts — privacy and preview terms draft

**Unpublished draft. Owner/controller details and legal review are required before
public use.** This is based on implemented behavior, not a claim that the remaining
privacy controls are complete. Do not link this as an approved policy in the app.

Required owner inputs: registered operator/company name, business country, postal
and privacy/support contact, applicable launch countries/age rule, approved data
locations/providers, exact retention/backup policy and complaint/escalation process.
The engineering launch blockers in STAGING_BLOCKERS.md remain binding.

## Privacy notice draft

**Who operates the service.** NextPhase Shorts is operated by [REGISTERED OPERATOR],
located in [BUSINESS COUNTRY], contact [APPROVED PRIVACY CONTACT]. The operator is
responsible for the data described here. These fields must be completed, not
inferred from a domain registrar, phone network or test email address.

**What we handle and why.** Account email, password hashes and session/recovery
records support authentication and security. Project titles, filenames, uploaded
video/audio, requested duration/style, upload checksums/offsets and rights receipt
support resumable transfer and server rendering. Job states, attempt/stage timings,
byte/resource measurements and limited operational identifiers support reliability,
security, cleanup and cost control. Passwords are not stored as plaintext. Session
and recovery handling use the protections documented in the auth runbooks.

**Video processing.** The current preview performs server-side first-seconds trim/
letterbox rendering to vertical MP4, up to the requested maximum and never above
60 seconds. It does not currently generate highlights, captions or AI style effects.
Heavy rendering is not run on the phone. Importing, uploading, playback and saving
still use device storage, network, power and data allowance.

**Your footage and rights.** Import is user initiated, not automatic gallery upload.
You must have the rights and necessary permissions to edit uploaded footage,
including depicted people/voices. The recorded acknowledgement is a user statement,
not independent rights verification. The current service does not send private
footage to an AI model or use it to train one. Any future third-party AI use requires
an approved policy and consent design before activation.

**Recipients and providers.** Approved deployment providers and locations must be
listed here before hosting real users. Optional password reset/verification uses
Resend only when the operator enables it; accepted provider transmission is not a
guarantee of inbox delivery. Provider/inbox copies have their own policies. Local
prototype media stays on the operator's configured private local or S3-compatible
store. Expo Go is a third-party development client with its own platform/privacy
behavior, not the final independently reviewed production app. No marketing
tracking, public checkout, subscription collection or third-party AI is enabled
by this preview build; do not infer future provider terms from that fact.

**Security and access.** API access is account scoped. Stored media is private;
short-lived signed links, where enabled, are capabilities until expiry/removal.
Saved, shared or already transmitted copies cannot be recalled. Public deployment
requires reviewed TLS, private network/IAM, backup and incident controls; local
USB development is not a public hosting security certification.

**Retention and deletion — current limits requiring review.** Projects are retained
until explicit deletion, with no surprise age expiry. Project/account deletion
revokes applicable access and schedules retryable media cleanup behind active
writer/capability deadlines. Outages/stopped maintenance can delay removal.
Operational trace observations and stopped-worker records have bounded default
seven-day aging; job/attempt/cost/rights/grant/deletion tombstones and crash metadata
are currently retained. Backups, provider/inbox copies, untracked historical stores,
versioned storage and saved/shared device copies are outside full erasure. **The
final user policy must state approved exact retention periods and exceptions;
engineering has not completed full personal-data/backup erasure.** A separately
protected later-deletion journal must prevent old backups resurrecting accounts
or footage before real-data restore/cutover.

**Requests and choices.** Account sign-out, password change, available email actions,
project deletion and account deletion are provided according to their server state.
For access/correction/export/complaint or help contact [APPROVED CONTACT]. A complete
self-service personal-data export is not currently implemented; do not advertise
one. Applicable legal rights, response periods, identity checks and local authority
contact must be finalized for the operator/launch jurisdiction.

**Children, international transfers, incidents and changes.** The operator must
approve an age/consent rule, cross-border/provider safeguards, incident notice
process and policy-change mechanism. None is silently declared complete by this
draft. Do not accept public users until these fields and operational controls are
reviewed and implemented.

## Preview terms draft

- The service produces short vertical exports, maximum 60 seconds. Current styles
  are roadmap labels; the baseline renderer does not add the planned AI effects.
  Review the result before relying on it or publishing it.
- You retain your footage rights. You grant only the permissions needed for the
  operator/approved processors to store, transfer, edit and return your requested
  export under the approved privacy notice; no training/resale permission is
  implied. The precise legal grant must be reviewed for the launch jurisdiction.
- Upload only material you may lawfully process. Do not use the service for illegal
  content, unauthorized identity/voice misuse, security abuse or rights infringement.
  Reporting, moderation, appeals and escalation contacts must be established before
  public launch; the prototype does not implement a complete moderation program.
- Upload/source size, duration, queue/storage/concurrency and fair-use limits apply.
  A capacity refusal is not a charge. No customer billing or subscription collection
  is active; any future paid terms, store compliance, credits, renewal/cancellation/
  refunds and taxes require separate reviewed activation and customer agreement.
- Network failures, permissions, device storage and provider/runtime outages can
  interrupt the preview. Resumable transfers require the app's saved private copy
  and metadata to remain intact. Keep the original recording. No fixed turnaround,
  quality, always-on background transfer or zero-battery-use promise is made.
- The operator must finalize support, acceptable-use enforcement, account suspension,
  content disputes, statutory consumer protections, liability/remedies, termination,
  governing law and dispute process. Do not insert a blanket exclusion of mandatory
  rights. These clauses are unresolved approval work, not agreed customer terms.

No policy/terms were published, no recipient was contacted, no provider contract
accepted and no legal approval inferred from preparing this draft.


Engineering draft update: independent encrypted **local** deletion/revocation
journaling, DB stream binding and explicit offline restore/release are implemented.
Protected restores invalidate all old credentials/passwords and require fresh
recovery; unbound/pre-activation snapshots are refused. This does not complete
immutable/offsite custody, encrypted snapshot retention, actual production fencing
or remote/versioned erasure. This draft remains unpublished and unapproved.
