import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./.data/nextphase.db")
        self.storage_dir = Path(os.getenv("STORAGE_DIR", "./.data/media")).resolve()
        self.jwt_secret = os.getenv("JWT_SECRET", "")
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", "314572800"))
        self.max_source_seconds = int(os.getenv("MAX_SOURCE_SECONDS", "600"))
        self.render_timeout_seconds = int(os.getenv("RENDER_TIMEOUT_SECONDS", "1200"))
        self.worker_poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
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
        self.storage_dir.mkdir(parents=True, exist_ok=True)

@lru_cache(maxsize=1)
def get_settings():
    return Settings()
