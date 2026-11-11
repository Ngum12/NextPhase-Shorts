"""Private English review and selected-excerpt queue admission; inference is offline."""
import hashlib
import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, UUID4
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis_annotations import TranscriptReview, fingerprint, validate_review
from .analysis_plan import ClosedModel, Digest, Proposal, Transcript, propose
from .auth import current_user
from .config import get_settings
from .db import session_dep
from .models import ProjectAnalysis, RenderJob, UploadSession, User, utcnow
from .queue import lock_owner

router = APIRouter(prefix='/api/v1/jobs', tags=['English review pilot'])
MAX_TRANSCRIPT_BYTES = 262144
MAX_WORDS = 1000
MAX_OWNER_ROWS = 10
MAX_GLOBAL_ROWS = 100
PRIVATE = {'Cache-Control': 'private, no-store'}


def require_enabled(owner):
    settings = get_settings()
    if not settings.english_review_enabled or owner not in settings.english_review_user_ids:
        raise HTTPException(404, 'English review is unavailable', headers=PRIVATE)


def owned_project(db, owner, job_id):
    require_enabled(owner)
    lock_owner(db, owner)
    job = db.scalar(select(RenderJob).where(RenderJob.id == job_id,
        RenderJob.user_id == owner, RenderJob.status != 'deleted',
        RenderJob.deleted_at.is_(None)).with_for_update())
    if job is None:
        raise HTTPException(404, 'Project not found', headers=PRIVATE)
    return job


def revision_for(transcript, review):
    content = fingerprint(transcript) + ':' + (fingerprint(review) if review else 'unreviewed')
    return hashlib.sha256(content.encode()).hexdigest()


def import_transcript(db, *, owner, job_id, transcript):
    """Trusted operator only: bind to the accepted upload's durable full checksum."""
    job = owned_project(db, owner, job_id)
    if job.preview_parent_id is not None:
        raise ValueError('Preview projects cannot become analysis sources')
    transcript = Transcript.model_validate(transcript)
    if (transcript.language != 'en' or not transcript.words or len(transcript.words) > MAX_WORDS
            or len(transcript.model_dump_json().encode()) > MAX_TRANSCRIPT_BYTES):
        raise ValueError('Transcript exceeds English review pilot profile')
    accepted = db.scalar(select(UploadSession).where(UploadSession.job_id == job_id,
        UploadSession.user_id == owner, UploadSession.status == 'completed'))
    if (accepted is None or accepted.source_sha256 != transcript.source_sha256
            or math.ceil(job.source_duration_seconds * 1000) != transcript.source_duration_ms):
        raise ValueError('Transcript differs from accepted project source')
    existing = db.get(ProjectAnalysis, job_id)
    if existing:
        if fingerprint(Transcript.model_validate_json(existing.transcript_json)) != fingerprint(transcript):
            raise ValueError('Existing analysis is preserved; use a new project')
        return existing  # Idempotent imports preserve all later human annotations.
    # Serialize bounded metadata admission after the existing owner lock.
    from .capacity import lock, disk_available
    lock(db)
    owner_count = db.scalar(select(func.count()).select_from(ProjectAnalysis)
        .join(RenderJob, RenderJob.id == ProjectAnalysis.job_id).where(RenderJob.user_id == owner))
    global_count = db.scalar(select(func.count()).select_from(ProjectAnalysis))
    if owner_count >= MAX_OWNER_ROWS or global_count >= MAX_GLOBAL_ROWS:
        raise ValueError('English review metadata capacity is full')
    disk_available(MAX_TRANSCRIPT_BYTES * 2)
    plan = propose(transcript, job.desired_seconds)
    row = ProjectAnalysis(job_id=job_id, transcript_json=transcript.model_dump_json(),
        review_json=None, proposal_json=plan.model_dump_json(), revision=revision_for(transcript, None))
    db.add(row)
    return row


def document(row):
    # Revalidate private records before exposing them; never return raw DB strings.
    transcript = Transcript.model_validate_json(row.transcript_json)
    proposal = Proposal.model_validate_json(row.proposal_json)
    review = TranscriptReview.model_validate_json(row.review_json) if row.review_json else None
    if review is not None:
        validate_review(transcript, review)
    if (transcript.language != 'en' or len(transcript.words)>MAX_WORDS
            or proposal.source_sha256 != transcript.source_sha256
            or proposal.review_sha256 != (fingerprint(review) if review else None)
            or proposal.transcript_sha256 != (fingerprint(transcript) if review else None)
            or row.revision != revision_for(transcript, review)):
        raise RuntimeError('Stored analysis identity differs')
    return {'job_id': row.job_id, 'revision': row.revision,
        'transcript_sha256': fingerprint(transcript),
        'transcript': transcript.model_dump(mode='json'),
        'review': review.model_dump(mode='json') if review else None,
        'proposal': proposal.model_dump(mode='json'), 'render_enabled': False,
        'queued_preview_supported': True, 'clean_captions_supported': True}


class PreviewRequest(ClosedModel):
    revision: Digest
    candidate_number: int = Field(strict=True,ge=1,le=5)
    idempotency_key: UUID4
    acknowledged_preview: bool = Field(strict=True)
    caption_style: Literal['none','clean-1']='none'


@router.post('/{job_id}/analysis/previews',status_code=202)
def queue_preview(job_id: str,payload: PreviewRequest,response: Response,
                  user: User=Depends(current_user),db: Session=Depends(session_dep)):
    import uuid
    from pathlib import Path
    from .excerpt_jobs import ExcerptSpec
    from .queue import admit_job
    from .schemas import JobResponse
    from .storage import reservation
    parent=owned_project(db,user.id,job_id)
    if not payload.acknowledged_preview:
        raise HTTPException(422,'Review the selected text before requesting a preview',headers=PRIVATE)
    if parent.preview_parent_id is not None or parent.media_backend!='local':
        raise HTTPException(409,'Preview requires an original local project',headers=PRIVATE)
    key='excerpt_'+str(payload.idempotency_key)
    identity=f'{parent.id}:{payload.revision}:{payload.candidate_number}'
    if payload.caption_style != 'none':identity += ':'+payload.caption_style
    request_hash=hashlib.sha256(identity.encode()).hexdigest()
    previous=db.scalar(select(RenderJob).where(RenderJob.user_id==user.id,RenderJob.idempotency_key==key))
    if previous:
        if previous.status=='deleted':raise HTTPException(410,'This preview was deleted; start a new request',headers=PRIVATE)
        if previous.request_hash!=request_hash:raise HTTPException(409,'Preview request key was already used',headers=PRIVATE)
        response.headers['Cache-Control']='private, no-store'
        result=JobResponse.model_validate(previous).model_dump(mode='json');db.commit();return result
    row=db.get(ProjectAnalysis,job_id)
    if row is None:raise HTTPException(404,'No English transcript is ready for this project',headers=PRIVATE)
    data=document(row)
    if row.revision!=payload.revision:
        raise HTTPException(409,'This review changed. Refresh before rendering.',headers=PRIVATE)
    if data['review'] is None:raise HTTPException(409,'Save your transcript review before rendering',headers=PRIVATE)
    plan=Proposal.model_validate_json(row.proposal_json)
    if payload.candidate_number>len(plan.candidates):raise HTTPException(422,'Choose an available clip suggestion',headers=PRIVATE)
    candidate=plan.candidates[payload.candidate_number-1]
    from .caption_plan import captions_for
    try:
        captions=captions_for(Transcript.model_validate_json(row.transcript_json), candidate) if payload.caption_style=='clean-1' else ()
    except ValueError:
        raise HTTPException(422,'This clip does not fit the clean caption limits. Choose a plain preview.',headers=PRIVATE) from None
    accepted=db.scalar(select(UploadSession).where(UploadSession.job_id==parent.id,
        UploadSession.user_id==user.id,UploadSession.status=='completed'))
    if accepted is None or accepted.source_sha256!=plan.source_sha256:
        raise HTTPException(409,'Accepted source identity is unavailable',headers=PRIVATE)
    spec=ExcerptSpec(source_sha256=plan.source_sha256,source_bytes=accepted.total_bytes,
        source_duration_ms=plan.source_duration_ms,source_extension=Path(parent.source_path).suffix.lower(),
        source_start_ms=candidate.source_start_ms,source_end_ms=candidate.source_end_ms,
        output_frames=candidate.output_frames,requested_seconds=parent.desired_seconds,
        review_sha256=plan.review_sha256,transcript_sha256=plan.transcript_sha256,
        review_revision=row.revision,candidate_number=payload.candidate_number,
        caption_style=payload.caption_style,captions=captions)
    settings=get_settings()
    if not 0<accepted.total_bytes<=min(settings.max_upload_bytes,314572800):
        raise HTTPException(409,'Source exceeds the preview profile',headers=PRIVATE)
    preview_cap=min(settings.max_render_bytes,64*1024**2)
    label='captions' if captions else 'preview'
    child=RenderJob(id=str(uuid.uuid4()),user_id=user.id,title=parent.title[:85]+f' · {label} {payload.candidate_number}',
        style=parent.style,desired_seconds=parent.desired_seconds,source_duration_seconds=parent.source_duration_seconds,
        source_path='',media_backend='local',status='queued',rights_version=parent.rights_version,
        rights_confirmed_at=parent.rights_confirmed_at,max_render_bytes=preview_cap,
        storage_reserved_bytes=reservation(2*accepted.total_bytes,preview_cap),
        idempotency_key=key,request_hash=request_hash,preview_parent_id=parent.id,preview_spec_json=spec.model_dump_json())
    child,_=admit_job(db,child)
    result=JobResponse.model_validate(child).model_dump(mode='json')
    db.commit();response.headers['Cache-Control']='private, no-store';return result


class SaveReview(ClosedModel):
    revision: Digest
    review: TranscriptReview


@router.get('/{job_id}/analysis')
def get_analysis(job_id: str, response: Response, user: User = Depends(current_user),
                 db: Session = Depends(session_dep)):
    response.headers['Cache-Control'] = 'private, no-store'
    owned_project(db, user.id, job_id)
    row = db.get(ProjectAnalysis, job_id)
    if row is None:
        raise HTTPException(404, 'No English transcript is ready for this project', headers=PRIVATE)
    result = document(row)
    db.commit()
    return result


@router.put('/{job_id}/analysis/review')
def save_review(job_id: str, payload: SaveReview, response: Response,
                user: User = Depends(current_user), db: Session = Depends(session_dep)):
    response.headers['Cache-Control'] = 'private, no-store'
    require_enabled(user.id)
    from .auth_limits import consume_limits
    consume_limits([('english-review-owner', user.id, 60)])
    job = owned_project(db, user.id, job_id)
    row = db.get(ProjectAnalysis, job_id)
    if row is None:
        raise HTTPException(404, 'No English transcript is ready for this project', headers=PRIVATE)
    transcript = Transcript.model_validate_json(row.transcript_json)
    try:
        review = validate_review(transcript, payload.review)
    except ValueError:
        raise HTTPException(422, 'Review does not match this transcript', headers=PRIVATE) from None
    revision = revision_for(transcript, review)
    if payload.revision != row.revision:
        # A lost success response may be retried; a different newer edit is fenced.
        if row.revision == revision:
            result = document(row)
            db.commit()
            return result
        raise HTTPException(409, 'This review changed. Refresh before saving again.', headers=PRIVATE)
    plan = propose(transcript, job.desired_seconds, review=review)
    row.review_json = review.model_dump_json()
    row.proposal_json = plan.model_dump_json()
    row.revision = revision
    row.updated_at = utcnow()
    result = document(row)
    db.commit()
    return result


def main():
    """Operator CLI also works inside the API image, reading private stdin."""
    import argparse
    import json
    import sys
    import uuid
    parser = argparse.ArgumentParser(description='Import a prepared English transcript for one private project')
    parser.add_argument('--owner', type=uuid.UUID, required=True)
    parser.add_argument('--project', type=uuid.UUID, required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--transcript')
    inputs.add_argument('--stdin-transcript', action='store_true')
    args = parser.parse_args()
    try:
        from .db import SessionLocal, engine
        from .migrate import require_current_schema
        require_current_schema(engine)
        if args.stdin_transcript:
            data = sys.stdin.buffer.read(MAX_TRANSCRIPT_BYTES+1)
        else:
            from .local_transcription import regular_file
            path = regular_file(args.transcript, maximum=MAX_TRANSCRIPT_BYTES)
            data = path.read_bytes()
        if not 0<len(data)<=MAX_TRANSCRIPT_BYTES:
            raise ValueError('Transcript exceeds English review pilot profile')
        transcript = Transcript.model_validate_json(data)
        with SessionLocal.begin() as db:
            import_transcript(db, owner=str(args.owner), job_id=str(args.project), transcript=transcript)
        print(json.dumps({'ok':True, 'imported':True, 'language':'en',
                          'asr_executed':False, 'render_enqueued':False}))
        return 0
    except Exception:
        print(json.dumps({'ok':False, 'issue':'analysis_import_refused', 'private_text_printed':False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
