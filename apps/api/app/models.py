import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, Index, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow():
    return datetime.now(timezone.utc)

def uuid_str():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    email_verification_method: Mapped[str | None] = mapped_column(String(24),nullable=True)
    jobs: Mapped[list["RenderJob"]] = relationship(back_populates="user")

class StorageBudget:
    storage_reserved_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_render_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AccountDeletion(Base):
    __tablename__ = 'account_deletions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    receipt_hash: Mapped[str] = mapped_column(String(64), unique=True)
    receipt_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cleanup_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    media_cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    namespaces: Mapped[str] = mapped_column(Text)


class RightsRecord:
    rights_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rights_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RenderJob(StorageBudget, RightsRecord, Base):
    __tablename__ = "render_jobs"
    __table_args__ = (Index("uq_render_jobs_owner_submission", "user_id", "idempotency_key", unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped["User"] = relationship(back_populates="jobs")
    trace_id: Mapped[str | None] = mapped_column(String(32),nullable=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(16),nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    style: Mapped[str] = mapped_column(String(48))
    desired_seconds: Mapped[int] = mapped_column(Integer)
    source_duration_seconds: Mapped[float] = mapped_column(Float)
    source_path: Mapped[str] = mapped_column(Text)
    media_backend: Mapped[str] = mapped_column(String(16), server_default='local')
    object_store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    media_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True,index=True)


class QueueSignal(Base):
    __tablename__='queue_signals'
    job_id: Mapped[str] = mapped_column(ForeignKey('render_jobs.id'),primary_key=True)
    generation: Mapped[str] = mapped_column(String(36),unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    next_publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36),nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)


class DeadLetter(Base):
    __tablename__='render_dead_letters'
    job_id: Mapped[str] = mapped_column(ForeignKey('render_jobs.id'),primary_key=True)
    reason: Mapped[str] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)


class UploadSession(StorageBudget, RightsRecord, Base):
    __tablename__ = 'upload_sessions'
    __table_args__ = (Index('uq_upload_sessions_owner_key', 'user_id', 'client_key', unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    client_key: Mapped[str] = mapped_column(String(128))
    descriptor_hash: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(120))
    style: Mapped[str] = mapped_column(String(48))
    desired_seconds: Mapped[int] = mapped_column(Integer)
    total_bytes: Mapped[int] = mapped_column(Integer)
    received_bytes: Mapped[int] = mapped_column(Integer, default=0)
    chunk_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='uploading')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey('render_jobs.id'), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parts_cleaned: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_backend: Mapped[str] = mapped_column(String(16), server_default='api')
    object_store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direct_cleanup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadPart(Base):
    __tablename__ = 'upload_parts'
    session_id: Mapped[str] = mapped_column(ForeignKey('upload_sessions.id'), primary_key=True)
    offset: Mapped[int] = mapped_column(Integer, primary_key=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    object_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    direct_grant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DirectUploadGrant(Base):
    __tablename__ = 'direct_upload_grants'
    __table_args__ = (Index('uq_direct_upload_offset', 'session_id', 'offset', unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey('upload_sessions.id'), index=True)
    offset: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256(jti), never the bearer token
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    family_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class RefreshFamily(Base):
    __tablename__ = 'refresh_families'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshGrant(Base):
    __tablename__ = 'refresh_grants'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey('refresh_families.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    successor_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuthRateBucket(Base):
    __tablename__ = 'auth_rate_buckets'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # HMAC identity; no plaintext IP/email
    attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RenderAttempt(Base):
    __tablename__ = 'render_attempts'
    __table_args__ = (Index('uq_render_attempt_number', 'job_id', 'number', unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('render_jobs.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='running')
    wall_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)


class WorkerPulse(Base):
    __tablename__='worker_pulses'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    phase: Mapped[str] = mapped_column(String(24))
    heartbeat_seconds: Mapped[float] = mapped_column(Float)


class AuthAction(Base):
    __tablename__='auth_actions'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64),unique=True)
    account_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    delivery_method: Mapped[str] = mapped_column(String(16),server_default='local_file')


class MailOutbox(Base):
    __tablename__ = 'mail_outbox'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey('auth_actions.id'),unique=True)
    payload: Mapped[str | None] = mapped_column(Text,nullable=True)  # authenticated encryption; no plaintext secrets
    state: Mapped[str] = mapped_column(String(16),default='pending',index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)
    attempts: Mapped[int] = mapped_column(Integer,default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36),nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    last_code: Mapped[str | None] = mapped_column(String(32),nullable=True)


class MailBudget(Base):
    __tablename__ = 'mail_budgets'
    id: Mapped[str] = mapped_column(String(16),primary_key=True)
    day: Mapped[str] = mapped_column(String(10))
    month: Mapped[str] = mapped_column(String(7))
    daily_attempts: Mapped[int] = mapped_column(Integer)
    monthly_attempts: Mapped[int] = mapped_column(Integer)
    next_send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    __tablename__='observations'
    id: Mapped[str] = mapped_column(String(16),primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32),index=True)
    parent_id: Mapped[str | None] = mapped_column(String(16),nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey('render_jobs.id'),nullable=True,index=True)
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey('render_attempts.id'),nullable=True)
    stage: Mapped[str] = mapped_column(String(32))
    started_ns: Mapped[int] = mapped_column(BigInteger,index=True)
    ended_ns: Mapped[int] = mapped_column(BigInteger)
    outcome: Mapped[str] = mapped_column(String(16))
    attributes: Mapped[str] = mapped_column(Text)


class ArtifactMeasure(Base):
    __tablename__='artifact_measures'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uuid_str)
    job_id: Mapped[str] = mapped_column(ForeignKey('render_jobs.id'),index=True)
    kind: Mapped[str] = mapped_column(String(16))
    bytes: Mapped[int] = mapped_column(BigInteger)
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CapacityGate(Base):
    __tablename__='capacity_gate'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)


class IngressLease(Base):
    __tablename__='ingress_leases'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True)


class RestoreJournalBinding(Base):
    __tablename__='restore_journal_binding'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    journal_id: Mapped[str] = mapped_column(String(36))
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
