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
        self.cors_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8081").split(",") if x.strip()]
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must have at least 32 characters")
        if self.env == "production" and "dev-only" in self.jwt_secret.lower():
            raise RuntimeError("Set a strong random JWT_SECRET before production")
        if self.env == "production" and self.database_url.startswith("sqlite"):
            raise RuntimeError("Production requires PostgreSQL and migrations")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

@lru_cache(maxsize=1)
def get_settings():
    return Settings()
