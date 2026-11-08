"""QA-only subprocess adapter. Captures synthetic messages locally; NEVER contacts Resend."""
import json
import os
from pathlib import Path
import uuid
import httpx


def main():
    if os.environ.get('APP_ENV')!='test' or os.environ.get('NEXTPHASE_MAIL_FIXTURE')!='local-only':
        raise RuntimeError('Only the isolated mail smoke may run this fixture')
    root=Path(os.environ['NEXTPHASE_MAIL_FIXTURE_DIR']);root.mkdir(mode=0o700,exist_ok=True)
    from app import mail_transport
    def handler(request):
        assert str(request.url)==mail_transport.ENDPOINT
        identity=str(uuid.UUID(request.headers['idempotency-key'].removeprefix('auth-')))
        path=root/(identity+'.json');payload=json.loads(request.content)
        if path.exists():assert json.loads(path.read_text())==payload
        else:
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w') as stream:json.dump(payload,stream)
        # Simulate provider acceptance then a hard sender death before DB ACK.
        # The second process sees the same idempotency key and same frozen body.
        marker=root/'crashed-once'
        if not marker.exists():marker.touch(mode=0o600);os._exit(99)
        return httpx.Response(200,json={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,identity))})
    mail_transport.make_client=lambda:httpx.Client(transport=httpx.MockTransport(handler))
    from app.mail_worker import main as run
    run()


if __name__=='__main__':main()
