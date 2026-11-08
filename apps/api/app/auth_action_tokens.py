"""Opaque action capabilities, credential binding and transactional invalidation."""
import hashlib,hmac
from sqlalchemy import update,select
from .config import get_settings
from .models import AuthAction,MailOutbox,utcnow


def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()


def account_digest(user):
    material='auth-action\0'+user.id+'\0'+user.email+'\0'+user.password_hash
    return hmac.new(get_settings().jwt_secret.encode(),material.encode(),hashlib.sha256).hexdigest()


def invalidate_actions(db,user_id,purpose=None):
    query=update(AuthAction).where(AuthAction.user_id==user_id,AuthAction.used_at.is_(None))
    if purpose:query=query.where(AuthAction.purpose==purpose)
    db.execute(query.values(used_at=utcnow()))
    actions=select(AuthAction.id).where(AuthAction.user_id==user_id)
    if purpose:actions=actions.where(AuthAction.purpose==purpose)
    db.execute(update(MailOutbox).where(MailOutbox.action_id.in_(actions),MailOutbox.state.in_(('pending','retry','sending')))
        .values(state='cancelled',payload=None,lease_token=None,lease_until=None,last_code='action_revoked'))
