"""Fixed-origin Resend transport. No endpoints, templates or headers from clients."""
import json
import time
import uuid
import httpx
from .config import get_settings

ENDPOINT='https://api.resend.com/emails'


class MailFailure(Exception):
    def __init__(self,code,retry=False,delay=30):
        self.code=code;self.retry=retry;self.delay=delay
        super().__init__(code)  # Never preserve provider bodies/headers or exception text.


def make_client():
    return httpx.Client(timeout=httpx.Timeout(10),follow_redirects=False)


def send(payload,key):
    settings=get_settings()
    if settings.auth_mail_backend!='resend' or not settings.auth_mail_send_enabled:
        raise MailFailure('sending_disabled',retry=True)
    try:
        with make_client() as client:
            began=time.monotonic()
            with client.stream('POST',ENDPOINT,headers={'Authorization':'Bearer '+settings.resend_api_key,
                    'Idempotency-Key':'auth-'+str(uuid.UUID(key))},json=payload) as response:
                if response.status_code==429:
                    retry=response.headers.get('Retry-After','30')
                    delay=min(86400,max(1,int(retry))) if retry.isdigit() and len(retry)<=6 else 30
                    raise MailFailure('provider_rate_limit',retry=True,delay=delay)
                if response.status_code>=500:raise MailFailure('provider_unavailable',retry=True)
                if response.status_code in (408,409):raise MailFailure('provider_in_progress',retry=True)
                if response.status_code not in (200,201):raise MailFailure('provider_rejected')
                body=b''
                for chunk in response.iter_bytes():
                    body+=chunk
                    if len(body)>4096 or time.monotonic()-began>20:raise MailFailure('provider_reply_invalid',retry=True)
                try:uuid.UUID(json.loads(body)['id'])
                except (ValueError,TypeError,KeyError):raise MailFailure('provider_reply_invalid',retry=True) from None
    except httpx.HTTPError:
        raise MailFailure('provider_network',retry=True) from None
