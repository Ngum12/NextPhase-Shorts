import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from .secret_config import read_secret

load_dotenv()

class Settings:
    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")
        self.gemini_planning_enabled=os.getenv('GEMINI_PLANNING_ENABLED','false').lower()=='true'
        self.gemini_free_tier_confirmed=os.getenv('GEMINI_FREE_TIER_CONFIRMED','false').lower()=='true'
        self.gemini_api_key=read_secret('GEMINI_API_KEY','')
        self.gemini_model='gemini-3.1-flash-lite'
        self.gemini_daily_limit=20
        self.gemini_owner_daily_limit=5
        self.english_review_enabled=os.getenv('ENGLISH_REVIEW_ENABLED','false').lower()=='true'
        self.english_review_user_ids=tuple(filter(None,(p.strip() for p in os.getenv('ENGLISH_REVIEW_USER_IDS','').split(','))))
        self.english_analysis_enabled=os.getenv('ENGLISH_ANALYSIS_ENABLED','false').lower()=='true'
        self.english_analysis_model_sha256=os.getenv('ENGLISH_ANALYSIS_MODEL_SHA256','')
        self.english_analysis_timeout_seconds=900
        if self.english_analysis_enabled:
            import re
            if (not self.english_review_enabled or self.env not in ('development','test')
                    or not re.fullmatch(r'[0-9a-f]{64}',self.english_analysis_model_sha256)):
                raise RuntimeError('English analysis requires the private review profile and verified model')
        if self.english_review_enabled:
            import uuid
            try:
                valid=(self.env in ('development','test') and 1<=len(self.english_review_user_ids)<=5
                       and all(str(uuid.UUID(p))==p for p in self.english_review_user_ids))
            except ValueError:valid=False
            if not valid:raise RuntimeError('English review pilot needs development/test mode and 1–5 canonical owner IDs')
        self.database_url = read_secret("DATABASE_URL", "sqlite:///./.data/nextphase.db")
        self.budget_state_file=os.getenv('BUDGET_STATE_FILE','')
        self.restore_journal_dir=os.getenv('RESTORE_JOURNAL_DIR','')
        self.restore_journal_key=read_secret('RESTORE_JOURNAL_KEY','')
        if bool(self.restore_journal_dir)!=bool(self.restore_journal_key):
            raise RuntimeError('Restore journal requires both an independent directory and key')
        if self.restore_journal_dir:
            from cryptography.fernet import Fernet
            try:Fernet(self.restore_journal_key.encode())
            except Exception:raise RuntimeError('Invalid restore journal key') from None
        self.storage_dir = Path(os.getenv("STORAGE_DIR", "./.data/media")).resolve()
        # Opt-in only. Existing rows retain their own backend across config changes.
        self.media_backend = os.getenv('MEDIA_BACKEND', 'local')
        self.s3_endpoint = os.getenv('S3_ENDPOINT', '')
        self.s3_public_endpoint = os.getenv('S3_PUBLIC_ENDPOINT', self.s3_endpoint)
        self.s3_bucket = os.getenv('S3_BUCKET', '')
        self.s3_region = os.getenv('S3_REGION', 'us-east-1')
        self.s3_access_key = read_secret('S3_ACCESS_KEY_ID', '')
        self.s3_secret_key = read_secret('S3_SECRET_ACCESS_KEY', '')
        self.signed_download_seconds = int(os.getenv('SIGNED_DOWNLOAD_SECONDS', '60'))
        self.direct_uploads_enabled = os.getenv('DIRECT_UPLOADS_ENABLED', 'false').lower() == 'true'
        self.signed_upload_seconds = int(os.getenv('SIGNED_UPLOAD_SECONDS', '60'))
        if not 5 <= self.signed_upload_seconds <= 60:
            raise RuntimeError('Signed upload lifetime must be 5–60 seconds')
        if self.direct_uploads_enabled and self.media_backend != 's3':
            raise RuntimeError('Direct uploads require S3 media storage')
        if self.media_backend not in ('local', 's3') or not 5 <= self.signed_download_seconds <= 60:
            raise RuntimeError('Invalid media backend or signed download lifetime (5–60 seconds)')
        if self.media_backend == 's3':
            self.validate_s3()
        self.auth_mail_backend=os.getenv('AUTH_MAIL_BACKEND','disabled')
        self.auth_mail_dir=Path(os.getenv('AUTH_MAIL_DIR',str(self.storage_dir.parent/'auth-mail'))).absolute()
        self.auth_action_minutes=int(os.getenv('AUTH_ACTION_MINUTES','15'))
        self.auth_action_email_limit=int(os.getenv('AUTH_ACTION_EMAIL_LIMIT','3'))
        self.auth_mail_send_enabled=os.getenv('AUTH_MAIL_SEND_ENABLED','false').lower()=='true'
        self.resend_api_key=read_secret('RESEND_API_KEY','')
        self.auth_mail_from=os.getenv('AUTH_MAIL_FROM','')
        self.auth_mail_keys=[part.strip() for part in read_secret('AUTH_MAIL_ENCRYPTION_KEYS','').split(',') if part.strip()]
        self.auth_mail_recipients=tuple(part.strip().lower() for part in os.getenv('AUTH_MAIL_RECIPIENTS','').split(',') if part.strip())
        self.auth_mail_daily_limit=int(os.getenv('AUTH_MAIL_DAILY_LIMIT','20'))
        self.auth_mail_monthly_limit=int(os.getenv('AUTH_MAIL_MONTHLY_LIMIT','500'))
        self.auth_require_verified_email=os.getenv('AUTH_REQUIRE_VERIFIED_EMAIL','false').lower()=='true'
        if self.auth_mail_backend not in ('disabled','file','resend'):
            raise RuntimeError('Invalid authentication mail backend')
        if not 1<=self.auth_mail_daily_limit<=100 or not self.auth_mail_daily_limit<=self.auth_mail_monthly_limit<=3000:
            raise RuntimeError('Mail attempt caps require 1–100/day and daily–3000/month')
        if self.auth_mail_send_enabled and self.auth_mail_backend!='resend':
            raise RuntimeError('Real email sending requires the resend backend')
        if self.auth_mail_keys:
            from cryptography.fernet import Fernet
            try:
                for key in self.auth_mail_keys:Fernet(key.encode())
            except (ValueError,TypeError):raise RuntimeError('Invalid mail encryption key configuration') from None
        if self.auth_mail_send_enabled:
            from email_validator import validate_email,EmailNotValidError
            try:
                validate_email(self.auth_mail_from,check_deliverability=False)
                for address in self.auth_mail_recipients:validate_email(address,check_deliverability=False)
            except EmailNotValidError:raise RuntimeError('Invalid mail sender or recipient configuration') from None
            if not self.auth_mail_keys or not 16<=len(self.resend_api_key)<=512 or any(c.isspace() for c in self.resend_api_key):
                raise RuntimeError('Real mail requires separate encryption keys and a server API key')
            if self.env in ('development','test') and not 1<=len(self.auth_mail_recipients)<=5:
                raise RuntimeError('Development email requires an explicit 1–5 recipient allowlist')
        if self.auth_require_verified_email and not (self.auth_mail_backend=='resend' and self.auth_mail_send_enabled):
            raise RuntimeError('Verified-upload policy requires enabled real email delivery')
        if self.auth_mail_backend=='file' and self.env not in ('development','test'):
            raise RuntimeError('Local file mail is forbidden in staging/production')
        if self.auth_mail_dir.resolve()==self.storage_dir or self.storage_dir in self.auth_mail_dir.resolve().parents:
            raise RuntimeError('Authentication mail must be outside media storage')
        if not 5<=self.auth_action_minutes<=30 or not 1<=self.auth_action_email_limit<=20:
            raise RuntimeError('Auth actions require 5–30 minute expiry and 1–20 requests per email window')
        self.jwt_secret = read_secret("JWT_SECRET", "")
        if self.jwt_secret and self.jwt_secret in self.auth_mail_keys:
            raise RuntimeError('Mail encryption keys must be separate from the session secret')
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", "314572800"))
        self.account_storage_bytes = int(os.getenv('ACCOUNT_STORAGE_BYTES','5368709120'))
        self.max_render_bytes = int(os.getenv('MAX_RENDER_BYTES','67108864'))
        if self.account_storage_bytes < 1 or not 1048576 <= self.max_render_bytes <= 536870912:
            raise RuntimeError('Storage budget must be positive; render cap must be 1–512 MiB')
        self.max_source_seconds = int(os.getenv("MAX_SOURCE_SECONDS", "600"))
        self.render_timeout_seconds = int(os.getenv("RENDER_TIMEOUT_SECONDS", "1200"))
        self.worker_heartbeat_seconds=int(os.getenv('WORKER_HEARTBEAT_SECONDS','10'))
        if not 1<=self.worker_heartbeat_seconds<=60:
            raise RuntimeError('Worker heartbeat must be 1–60 seconds')
        self.worker_poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
        self.worker_require_limits = os.getenv('WORKER_REQUIRE_LIMITS','false').lower()=='true'
        self.worker_require_sandbox=os.getenv('WORKER_REQUIRE_SANDBOX','false').lower()=='true'
        self.queue_backend=os.getenv('QUEUE_BACKEND','database')
        self.queue_host=os.getenv('QUEUE_HOST','127.0.0.1')
        self.queue_port=int(os.getenv('QUEUE_PORT','6379'))
        self.queue_password=read_secret('QUEUE_PASSWORD','')
        self.queue_tls=os.getenv('QUEUE_TLS','false').lower()=='true'
        self.worker_lease_seconds=int(os.getenv('WORKER_LEASE_SECONDS','45'))
        self.worker_renew_seconds=int(os.getenv('WORKER_RENEW_SECONDS','10'))
        self.retry_backoff_seconds=int(os.getenv('RETRY_BACKOFF_SECONDS','5'))
        if self.queue_backend not in ('database','valkey') or not 1<=self.queue_port<=65535:
            raise RuntimeError('Invalid queue configuration')
        if not 15<=self.worker_lease_seconds<=120 or not 1<=self.worker_renew_seconds<=self.worker_lease_seconds//3:
            raise RuntimeError('Worker lease must be 15–120 seconds with renewal <= one third')
        if not 1<=self.retry_backoff_seconds<=300:
            raise RuntimeError('Retry backoff must be 1–300 seconds')
        if self.queue_backend=='valkey':
            import re
            if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}',self.queue_host) or len(self.queue_password)<32:
                raise RuntimeError('Valkey requires an explicit host and strong server-only password')
            if self.env in ('staging','production') and not self.queue_tls:
                raise RuntimeError('Staging/production queue requires verified TLS')
        import math
        if not 1<=self.render_timeout_seconds<=7200 or not math.isfinite(self.worker_poll_seconds) or not .05<=self.worker_poll_seconds<=60:
            raise RuntimeError('Render timeout must be 1–7200 seconds; worker poll must be 0.05–60 seconds')
        self.api_request_concurrency=int(os.getenv('API_REQUEST_CONCURRENCY','8'))
        self.global_active_limit=int(os.getenv('GLOBAL_ACTIVE_LIMIT','100'))
        self.global_processing_limit=int(os.getenv('GLOBAL_PROCESSING_LIMIT','2'))
        self.global_storage_bytes=int(os.getenv('GLOBAL_STORAGE_BYTES','53687091200'))
        self.global_ingress_bytes=int(os.getenv('GLOBAL_INGRESS_BYTES','1073741824'))
        self.ingress_limit=int(os.getenv('INGRESS_LIMIT','4'))
        self.min_free_disk_bytes=int(os.getenv('MIN_FREE_DISK_BYTES','134217728'))
        self.ingress_timeout_seconds=int(os.getenv('INGRESS_TIMEOUT_SECONDS','600'))
        self.observation_retention_days=int(os.getenv('OBSERVATION_RETENTION_DAYS','7'))
        if not (1<=self.api_request_concurrency<=12 and 1<=self.global_processing_limit<=self.global_active_limit<=10000 and
                self.global_storage_bytes>0 and self.global_ingress_bytes>0 and 1<=self.ingress_limit<=100 and
                self.min_free_disk_bytes>=0 and 30<=self.ingress_timeout_seconds<=1800 and
                1<=self.observation_retention_days<=30):
            raise RuntimeError('Invalid global capacity or observation retention configuration')
        self.max_active_jobs_per_user = int(os.getenv("MAX_ACTIVE_JOBS_PER_USER", "3"))
        self.max_processing_jobs_per_user = int(os.getenv("MAX_PROCESSING_JOBS_PER_USER", "1"))
        if not 1 <= self.max_processing_jobs_per_user <= self.max_active_jobs_per_user:
            raise RuntimeError("Queue limits must be positive and processing must not exceed active jobs")
        self.upload_chunk_bytes = int(os.getenv("UPLOAD_CHUNK_BYTES", "1048576"))
        self.upload_part_timeout_seconds = int(os.getenv("UPLOAD_PART_TIMEOUT_SECONDS", "120"))
        if not 5 <= self.upload_part_timeout_seconds <= 600:
            raise RuntimeError("Upload part timeout must be 5–600 seconds")
        self.upload_session_hours = int(os.getenv("UPLOAD_SESSION_HOURS", "24"))
        if not 65536 <= self.upload_chunk_bytes <= 8388608 or not 1 <= self.upload_session_hours <= 168:
            raise RuntimeError("Upload chunks must be 64 KiB–8 MiB and session lifetime 1–168 hours")
        self.auth_session_hours = int(os.getenv("AUTH_SESSION_HOURS", "24"))
        self.auth_access_minutes = int(os.getenv('AUTH_ACCESS_MINUTES', '15'))
        self.auth_refresh_days = int(os.getenv('AUTH_REFRESH_DAYS', '30'))
        self.auth_refresh_idle_days = int(os.getenv('AUTH_REFRESH_IDLE_DAYS', '7'))
        self.auth_refresh_retry_seconds = int(os.getenv('AUTH_REFRESH_RETRY_SECONDS', '120'))
        self.auth_refresh_ip_limit = int(os.getenv('AUTH_REFRESH_IP_LIMIT', '120'))
        if not (1 <= self.auth_access_minutes <= 60 and 1 <= self.auth_refresh_idle_days <= self.auth_refresh_days <= 30
                and 30 <= self.auth_refresh_retry_seconds <= 300 and self.auth_refresh_ip_limit > 0):
            raise RuntimeError('Invalid access or refresh session limits')
        self.auth_window_seconds = int(os.getenv("AUTH_WINDOW_SECONDS", "900"))
        self.auth_login_account_limit = int(os.getenv("AUTH_LOGIN_ACCOUNT_LIMIT", "5"))
        self.auth_login_ip_limit = int(os.getenv("AUTH_LOGIN_IP_LIMIT", "30"))
        self.auth_register_ip_limit = int(os.getenv("AUTH_REGISTER_IP_LIMIT", "10"))
        self.auth_password_limit = int(os.getenv("AUTH_PASSWORD_LIMIT", "5"))
        if not 1 <= self.auth_session_hours <= 72 or not 10 <= self.auth_window_seconds <= 3600:
            raise RuntimeError("Auth session hours must be 1–72 and rate windows 10–3600 seconds")
        if min(self.auth_login_account_limit, self.auth_login_ip_limit,
               self.auth_register_ip_limit, self.auth_password_limit) < 1:
            raise RuntimeError("Authentication rate limits must be positive")
        self.cors_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8081").split(",") if x.strip()]
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must have at least 32 characters")
        if self.env == "production" and "dev-only" in self.jwt_secret.lower():
            raise RuntimeError("Set a strong random JWT_SECRET before production")
        if self.env in {"staging", "production"} and not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Staging and production require PostgreSQL and migrations")
        if self.env in {'staging','production'} and not self.budget_state_file:
            raise RuntimeError('Staging and production require an operator budget state file')
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def validate_s3(self):
        from urllib.parse import urlsplit
        import re
        if not all((self.s3_bucket, self.s3_access_key, self.s3_secret_key)):
            raise RuntimeError('S3 requires an explicit bucket and scoped server credentials')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.s3_bucket):
            raise RuntimeError('Invalid S3 bucket name')
        for endpoint in (self.s3_endpoint, self.s3_public_endpoint):
            url = urlsplit(endpoint)
            if (url.scheme not in ('http', 'https') or not url.hostname or url.username or
                    url.password or url.path not in ('', '/') or url.query or url.fragment):
                raise RuntimeError('S3 endpoint must be an explicit HTTP(S) origin')
            if url.scheme != 'https' and (self.env not in ('development', 'test') or
                    url.hostname not in ('localhost', '127.0.0.1', 's3')):
                raise RuntimeError('HTTP S3 is allowed only for local development endpoints')

@lru_cache(maxsize=1)
def get_settings():
    return Settings()
