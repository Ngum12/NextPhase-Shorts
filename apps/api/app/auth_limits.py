"""Shared atomic fixed windows; keys are HMACs, not plaintext account/IP data."""
import hashlib
import hmac
import math
from datetime import timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .config import get_settings
from .db import SessionLocal, engine
from .models import AuthRateBucket, AuthSession, utcnow


def consume_limits(identities):
    settings = get_settings()
    now = utcnow()
    expiry = now + timedelta(seconds=settings.auth_window_seconds)
    table = AuthRateBucket.__table__
    insert = pg_insert if engine.dialect.name == 'postgresql' else sqlite_insert
    retry = 0
    with SessionLocal.begin() as db:
        for purpose, identity, limit in identities:
            key = hmac.new(settings.jwt_secret.encode(), (purpose+'\0'+identity).encode(), hashlib.sha256).hexdigest()
            expired = table.c.expires_at <= now
            statement = insert(table).values(key=key, attempts=1, expires_at=expiry)
            statement = statement.on_conflict_do_update(index_elements=['key'], set_={
                'attempts': case((expired, 1), (table.c.attempts >= limit, limit+1), else_=table.c.attempts+1),
                'expires_at': case((expired, expiry), else_=table.c.expires_at),
            }).returning(table.c.attempts, table.c.expires_at)
            count, end = db.execute(statement).one()
            if count > limit:
                end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
                retry = max(retry, math.ceil((end-now).total_seconds()), 1)
                break  # A blocked peer cannot create unbounded account buckets.
    # Commit even denied attempts; raising inside the transaction would undo the limit.
    if retry:
        raise HTTPException(429, 'Too many authentication attempts. Try again later.', headers={'Retry-After': str(retry)})


def cleanup_auth():
    now = utcnow()
    with SessionLocal.begin() as db:
        db.execute(delete(AuthRateBucket).where(AuthRateBucket.expires_at <= now))
        db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
