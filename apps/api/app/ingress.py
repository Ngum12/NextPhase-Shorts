"""Bound ASGI bodies before multipart parsing; reserve shared intake scratch."""
import time
import asyncio
from weakref import WeakKeyDictionary
import anyio
from fastapi import HTTPException
from starlette.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from .config import get_settings
from .capacity import acquire_ingress,release_ingress

class IngressGuard:
    def __init__(self,app):self.app=app;self.gates=WeakKeyDictionary()
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        # Keep request dependencies below the DB pool capacity. Await asynchronously
        # instead of consuming all sync worker threads waiting for a connection.
        loop=asyncio.get_running_loop()
        gate=self.gates.setdefault(loop,asyncio.Semaphore(get_settings().api_request_concurrency))
        try:
            with anyio.fail_after(30):await gate.acquire()
        except TimeoutError:
            return await JSONResponse({'detail':'Server request capacity is full; retry later'},status_code=503,headers={'Retry-After':'30'})(scope,receive,send)
        try:return await self.handle(scope,receive,send)
        finally:gate.release()

    async def handle(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method') not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        settings=get_settings();path=scope.get('path','')
        legacy=scope.get('method')=='POST' and path=='/api/v1/jobs'
        part=scope.get('method')=='PUT' and path.startswith('/api/v1/upload-sessions/') and path.endswith('/parts')
        limit=settings.max_upload_bytes+65536 if legacy else settings.upload_chunk_bytes if part else 65536
        received=0;lease=None;started=False;deadline=time.monotonic()+settings.ingress_timeout_seconds
        async def safe_send(message):
            nonlocal started
            if message['type']=='http.response.start':started=True
            await send(message)
        async def bounded_receive():
            nonlocal received
            remaining=deadline-time.monotonic()
            if remaining<=0:raise HTTPException(408,'Upload request timed out')
            try:
                with anyio.fail_after(remaining):message=await receive()
            except TimeoutError:raise HTTPException(408,'Upload request timed out') from None
            if message['type']=='http.request':
                received+=len(message.get('body',b''))
                if received>limit:raise HTTPException(413,'Request body exceeds the server limit')
            return message
        try:
            lengths=[value for key,value in scope.get('headers',[]) if key.lower()==b'content-length']
            if len(lengths)>1:raise HTTPException(400,'Invalid request length')
            if lengths:
                try:declared=int(lengths[0])
                except ValueError:raise HTTPException(400,'Invalid request length') from None
                if declared<0:raise HTTPException(400,'Invalid request length')
                if declared>limit:raise HTTPException(413,'Request body exceeds the server limit')
                limit=declared
            if legacy or part:
                lease=await anyio.to_thread.run_sync(acquire_ingress,limit*2)
            await self.app(scope,bounded_receive,safe_send)
        except HTTPException as error:
            if not started:await JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)(scope,receive,send)
            else:raise
        except SQLAlchemyError:
            if not started:await JSONResponse({'detail':'Server capacity is temporarily unavailable'},status_code=503,headers={'Retry-After':'30'})(scope,receive,send)
            else:raise
        finally:
            if lease:
                with anyio.CancelScope(shield=True):await anyio.to_thread.run_sync(release_ingress,lease)
