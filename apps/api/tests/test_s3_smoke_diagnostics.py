"""Failure diagnostics must not publish local credentials or URL capabilities."""
import importlib.util
from pathlib import Path
from botocore.exceptions import ClientError, EndpointConnectionError

spec = importlib.util.spec_from_file_location('s3_smoke_diagnostics',
    Path(__file__).resolve().parents[3]/'scripts/smoke_object_store.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_startup_log_redacts_credentials_and_signed_url_parameters():
    raw = ('access=test-access secret=test-secret '
           'http://localhost/bucket/key?X-Amz-Credential=test-access%2Fscope'
           '&X-Amz-Signature=private-signature&X-Amz-Security-Token=private-token\n'
           'permission denied /data/s3.json')
    result = smoke.sanitized_log(raw, 'test-access', 'test-secret')
    assert all(secret not in result for secret in
               ('test-access', 'test-secret', 'private-signature', 'private-token', '%2Fscope'))
    assert 'permission denied /data/s3.json' in result


def test_safe_error_exposes_service_code_but_never_request_or_message():
    error = ClientError({'Error': {'Code': 'AccessDenied',
        'Message': 'private-secret https://localhost?X-Amz-Signature=capability'}}, 'CreateBucket')
    assert smoke.safe_error(error) == 'ClientError:AccessDenied'
    assert smoke.safe_error(RuntimeError('private-secret')) == 'RuntimeError'
    assert smoke.safe_error(EndpointConnectionError(endpoint_url='http://private-secret')) == 'EndpointConnectionError'
    malicious = ClientError({'Error': {'Code': 'https://private-secret/path'}}, 'CreateBucket')
    assert smoke.safe_error(malicious) == 'ClientError'
