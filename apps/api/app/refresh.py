"""Opaque refresh rotation. Only keyed hashes and bounded retry metadata persist."""
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta, timezone

import jwt
from sqlalchemy import select, update
from .auth import ISSUER, AUDIENCE, unauthorized
from .config import get_settings
from .models import AuthSession, RefreshFamily, RefreshGrant, utcnow
from .queue import lock_owner


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def digest(purpose, value):
    return hmac.new(get_settings().jwt_secret.encode(), (purpose+'\0'+value).encode(), hashlib.sha256).hexdigest()


def replacement(purpose, token, key):
    raw = bytes.fromhex(digest(purpose, token+'\0'+key))
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def revoke_families(db, user_id, family_id=None):
    from .restore_journal import record
    record('revoke',user_id)
    families = update(RefreshFamily).where(RefreshFamily.user_id == user_id)
    sessions = update(AuthSession).where(AuthSession.user_id == user_id)
    if family_id is not None:
        families = families.where(RefreshFamily.id == family_id)
        sessions = sessions.where(AuthSession.family_id == family_id)
    db.execute(families.values(revoked_at=utcnow()))
    db.execute(sessions.values(revoked_at=utcnow()))


def pair(db, family, raw, nonce=None, session=None):
    now = utcnow()
    if session is None:
        nonce = nonce or secrets.token_urlsafe(32)
        session = AuthSession(id=hashlib.sha256(nonce.encode()).hexdigest(), user_id=family.user_id,
            family_id=family.id, created_at=now,
            expires_at=min(aware(family.expires_at), now+timedelta(minutes=get_settings().auth_access_minutes)))
        db.add(session)
    grant = db.get(RefreshGrant, digest('refresh-store', raw))
    access = jwt.encode({'sub': family.user_id, 'jti': nonce, 'iat': aware(session.created_at),
        'exp': aware(session.expires_at), 'iss': ISSUER, 'aud': AUDIENCE}, get_settings().jwt_secret, algorithm='HS256')
    return {'access_token': access, 'token_type': 'bearer',
        'expires_in': max(1, int((aware(session.expires_at)-now).total_seconds())),
        'refresh_token': raw, 'refresh_expires_in': max(1, int((aware(grant.expires_at)-now).total_seconds()))}


def issue_pair(db, user_id):
    family = RefreshFamily(user_id=user_id, expires_at=utcnow()+timedelta(days=get_settings().auth_refresh_days))
    db.add(family); db.flush()
    raw = secrets.token_urlsafe(32)
    db.add(RefreshGrant(token_hash=digest('refresh-store', raw), family_id=family.id,
        expires_at=min(aware(family.expires_at), utcnow()+timedelta(days=get_settings().auth_refresh_idle_days))))
    db.flush()
    return pair(db, family, raw)


def rotate(db, raw, key):
    grant = db.get(RefreshGrant, digest('refresh-store', raw))
    if grant is None:
        raise unauthorized()
    family = db.get(RefreshFamily, grant.family_id)
    lock_owner(db, family.user_id)
    db.refresh(family); db.refresh(grant)
    now = utcnow()
    if family.revoked_at or aware(family.expires_at) <= now:
        raise unauthorized()
    rotation_hash = digest('refresh-rotation', key)
    if grant.used_at is not None:
        if not hmac.compare_digest(grant.rotation_hash, rotation_hash):
            revoke_families(db, family.user_id, family.id)
            db.commit()  # Revocation must survive the HTTP 401 rollback path.
            raise unauthorized()
        successor = db.get(RefreshGrant, grant.successor_hash)
        session = db.get(AuthSession, grant.access_session_id)
        if (aware(grant.used_at)+timedelta(seconds=get_settings().auth_refresh_retry_seconds) <= now
                or successor is None or successor.used_at is not None or aware(successor.expires_at) <= now
                or session is None or session.revoked_at or aware(session.expires_at) <= now):
            raise unauthorized()
        return pair(db, family, replacement('refresh-next', raw, key),
            replacement('refresh-access', raw, key), session)
    if aware(grant.expires_at) <= now:
        raise unauthorized()
    next_raw = replacement('refresh-next', raw, key)
    nonce = replacement('refresh-access', raw, key)
    grant.used_at = now; grant.rotation_hash = rotation_hash
    grant.successor_hash = digest('refresh-store', next_raw)
    grant.access_session_id = hashlib.sha256(nonce.encode()).hexdigest()
    db.add(RefreshGrant(token_hash=grant.successor_hash, family_id=family.id,
        expires_at=min(aware(family.expires_at), now+timedelta(days=get_settings().auth_refresh_idle_days))))
    db.flush()
    return pair(db, family, next_raw, nonce)


def revoke_by_refresh(db, raw):
    grant = db.get(RefreshGrant, digest('refresh-store', raw))
    if grant:
        family = db.get(RefreshFamily, grant.family_id)
        lock_owner(db, family.user_id, allow_deleted=True)
        revoke_families(db, family.user_id, family.id)
