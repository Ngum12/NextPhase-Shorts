"""Expire upload reservations and remove terminal staging parts in bounded batches."""
from sqlalchemy import delete, select, update, or_, func
from .db import SessionLocal, engine
from .migrate import require_current_schema
from .models import UploadPart, UploadSession, utcnow
from .uploads import cleanup_parts


def cleanup_uploads(limit=100):
    with SessionLocal.begin() as db:
        db.execute(update(UploadSession).where(UploadSession.status == 'uploading',
            UploadSession.expires_at <= utcnow()).values(status='expired'))
        terminal = list(db.execute(select(UploadSession.id, UploadSession.user_id).where(
            UploadSession.status.in_(('completed', 'aborted', 'expired')),
            or_(UploadSession.parts_cleaned.is_(False), UploadSession.transfer_backend == 'direct-s3'))
            .order_by(func.coalesce(UploadSession.direct_cleanup_at, UploadSession.created_at)).limit(limit)))
    cleaned = 0
    for session_id, user_id in terminal:
        success = cleanup_parts(user_id, session_id)
        with SessionLocal.begin() as db:
            db.execute(update(UploadSession).where(UploadSession.id == session_id).values(
                direct_cleanup_at=utcnow(), parts_cleaned=success))
        if success:
            with SessionLocal.begin() as db:
                db.execute(delete(UploadPart).where(UploadPart.session_id == session_id))
                db.execute(update(UploadSession).where(UploadSession.id == session_id).values(parts_cleaned=True))
            cleaned += 1
    return cleaned


if __name__ == '__main__':
    require_current_schema(engine)
    print(f'Cleaned {cleanup_uploads()} terminal upload sessions.')
