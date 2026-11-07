"""Private, UUID-keyed S3 objects. No client-controlled URLs or bucket creation."""
import hashlib
import base64
import re
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import boto3
from botocore.session import Session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from .config import get_settings


class ObjectStoreError(RuntimeError):
    pass


def namespace_id():
    settings = get_settings()
    return hashlib.sha256((settings.s3_endpoint.rstrip('/') + '\n' + settings.s3_bucket).encode()).hexdigest()


def require_namespace(stored_id):
    if stored_id != namespace_id():
        raise ObjectStoreError('Private storage namespace changed; operator migration is required')


def prefix(owner, job):
    for value in (owner, job):
        if str(uuid.UUID(value)) != value:
            raise ValueError('Noncanonical media identity')
    return f'media/{owner}/{job}/'


def source_key(owner, job, extension):
    if extension not in ('.mp4', '.mov', '.m4v', '.webm'):
        raise ValueError('Unsupported source extension')
    return prefix(owner, job) + 'input' + extension


def output_key(owner, job, token):
    if str(uuid.UUID(token)) != token:
        raise ValueError('Noncanonical attempt identity')
    return prefix(owner, job) + token + '/output.mp4'


def upload_prefix(owner, session):
    return prefix(owner, session).replace('media/', 'uploads/', 1)


def upload_key(owner, session, grant, *, sealed=False):
    if str(uuid.UUID(grant)) != grant:
        raise ValueError('Noncanonical grant identity')
    return upload_prefix(owner, session) + ('sealed/' if sealed else 'incoming/') + grant


def signed_part(owner, session, grant, size, digest, seconds):
    checksum = base64.b64encode(bytes.fromhex(digest)).decode()
    headers = {'Content-Length': str(size), 'Content-Type': 'application/octet-stream',
               'x-amz-checksum-sha256': checksum, 'x-amz-meta-sha256': digest}
    try:
        url = client(public=True).generate_presigned_url('put_object', Params={
            'Bucket': get_settings().s3_bucket, 'Key': upload_key(owner, session, grant),
            'ContentLength': size, 'ContentType': headers['Content-Type'],
            'ChecksumSHA256': checksum, 'Metadata': {'sha256': digest}}, ExpiresIn=seconds)
        return {'url': url, 'headers': headers, 'expires_in_seconds': seconds}
    except (BotoCoreError, ClientError) as error:
        raise ObjectStoreError('Signed chunk storage is unavailable') from error


@lru_cache(maxsize=2)
def client(public=False):
    settings = get_settings()
    try:
        settings.validate_s3()
    except RuntimeError as error:
        raise ObjectStoreError('Private storage configuration is unavailable') from error
    # This adapter explicitly uses S3_* credentials, not a machine AWS profile or
    # metadata service. Keep the process environment and other clients untouched.
    session = Session(session_vars={'profile': (None, None, None, None)})
    sdk = boto3.Session(botocore_session=session)
    return sdk.client('s3', endpoint_url=settings.s3_public_endpoint if public else settings.s3_endpoint,
        region_name=settings.s3_region, aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=30,
                      retries={'total_max_attempts': 2, 'mode': 'standard'},
                      s3={'addressing_style': 'path'}))


def reference(key, digest):
    return f's3://{get_settings().s3_bucket}/{key}#{digest}'


def parse_reference(ref, expected_key):
    parsed = urlsplit(ref)
    if (parsed.scheme != 's3' or parsed.netloc != get_settings().s3_bucket or
            parsed.path != '/' + expected_key or parsed.query or
            not re.fullmatch('[a-f0-9]{64}', parsed.fragment)):
        raise ObjectStoreError('Invalid private object reference')
    return parsed.fragment


def put(path, key, max_bytes):
    """One bounded PUT; the private server-generated key is never signed for write."""
    try:
        size = path.stat().st_size
        if not 0 < size <= max_bytes:
            raise ObjectStoreError('Object exceeds its byte budget')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        with path.open('rb') as body:
            client().put_object(Bucket=get_settings().s3_bucket, Key=key, Body=body,
                ContentLength=size, ContentType='application/octet-stream',
                ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
                Metadata={'sha256': digest}, CacheControl='private, no-store')
        head = client().head_object(Bucket=get_settings().s3_bucket, Key=key)
        if head['ContentLength'] != size or head.get('Metadata', {}).get('sha256') != digest:
            raise ObjectStoreError('Stored object failed verification')
        return reference(key, digest)
    except (BotoCoreError, ClientError, OSError) as error:
        raise ObjectStoreError('Private storage is unavailable') from error


def open_object(ref, key, max_bytes):
    digest = parse_reference(ref, key)
    response = None
    try:
        response = client().get_object(Bucket=get_settings().s3_bucket, Key=key)
        if (not 0 < response['ContentLength'] <= max_bytes or
                response.get('Metadata', {}).get('sha256') != digest):
            raise ObjectStoreError('Stored object failed verification')
        return response
    except (BotoCoreError, ClientError, ObjectStoreError) as error:
        if response is not None:
            response['Body'].close()
        raise ObjectStoreError('Private video is unavailable') from error


def fetch(ref, key, destination, max_bytes):
    """Renderers receive only a bounded local file, never an S3/HTTP input URL."""
    response = open_object(ref, key, max_bytes)
    total = 0
    digest = hashlib.sha256()
    try:
        with destination.open('xb') as output:
            while chunk := response['Body'].read(65536):
                total += len(chunk)
                if total > max_bytes:
                    raise ObjectStoreError('Object exceeds its byte budget')
                digest.update(chunk)
                output.write(chunk)
        if total != response['ContentLength'] or digest.hexdigest() != parse_reference(ref, key):
            raise ObjectStoreError('Downloaded source failed integrity verification')
    except (BotoCoreError, OSError, ObjectStoreError) as error:
        destination.unlink(missing_ok=True)
        raise ObjectStoreError('Private source is unavailable') from error
    finally:
        response['Body'].close()


def signed_download(ref, key):
    parse_reference(ref, key)
    settings = get_settings()
    try:
        return client(public=True).generate_presigned_url('get_object', Params={
            'Bucket': settings.s3_bucket, 'Key': key,
            'ResponseContentType': 'video/mp4',
            'ResponseCacheControl': 'private, no-store',
            'ResponseContentDisposition': 'attachment; filename="nextphase-short.mp4"'},
            ExpiresIn=settings.signed_download_seconds)
    except (BotoCoreError, ClientError) as error:
        raise ObjectStoreError('Private storage is unavailable') from error


def remove_project(owner, job):
    """Retryable deletion of bounded, nonversioned project objects, including losers."""
    _remove_prefix(prefix(owner, job))


def remove_upload_session(owner, session):
    _remove_prefix(upload_prefix(owner, session))


def _remove_prefix(private_prefix):
    try:
        bucket = get_settings().s3_bucket
        if client().get_bucket_versioning(Bucket=bucket).get('Status') in ('Enabled', 'Suspended'):
            raise ObjectStoreError('Versioned buckets require version-aware erasure')
        for _ in range(10):
            page = client().list_objects_v2(Bucket=bucket, Prefix=private_prefix, MaxKeys=1000)
            objects = [{'Key': item['Key']} for item in page.get('Contents', [])]
            if not objects:
                return
            result = client().delete_objects(Bucket=bucket, Delete={'Objects': objects, 'Quiet': True})
            if result.get('Errors'):
                raise ObjectStoreError('Some private objects could not be removed')
        raise ObjectStoreError('Object cleanup batch limit reached; retry required')
    except (BotoCoreError, ClientError) as error:
        raise ObjectStoreError('Private storage cleanup is unavailable') from error


def check_bucket():
    """Readiness check, never creates/configures a cloud bucket or changes policies."""
    try:
        bucket = get_settings().s3_bucket
        client().head_bucket(Bucket=bucket)
        if client().get_bucket_versioning(Bucket=bucket).get('Status') in ('Enabled', 'Suspended'):
            raise ObjectStoreError('This increment requires a nonversioned private bucket')
    except (BotoCoreError, ClientError) as error:
        raise ObjectStoreError('Private storage is not ready') from error


def discard_unaccepted(owner, job):
    # Rejected uploads have no durable project. Best effort only; deployment needs
    # reconciliation/lifecycle handling for crashes and unavailable-store orphans.
    import logging
    try:
        remove_project(owner, job)
    except (ObjectStoreError, RuntimeError):
        logging.getLogger('nextphase.storage').warning('unaccepted object cleanup deferred')
