"""Allowlisted worker JSON events; no arbitrary messages, exception text or payloads."""
import json
import logging
import math
import uuid
from .models import utcnow

PHASES={'starting','maintenance','idle','rendering','database_retry','stopping','stopped'}
EVENTS={
    'worker_started':(logging.INFO,'worker started'),
    'worker_stopped':(logging.INFO,'worker stopped'),
    'database_unavailable':(logging.WARNING,'worker database unavailable; retrying'),
    'heartbeat_unavailable':(logging.WARNING,'worker heartbeat could not be recorded'),
    'render_completed':(logging.INFO,'render completed'),
    'render_stale':(logging.WARNING,'discarded stale render'),
    'render_cancelled':(logging.INFO,'render cancelled or lease lost'),
    'render_failed':(logging.WARNING,'media render failed'),
    'output_limit_exceeded':(logging.WARNING,'render output limit exceeded'),
    'storage_unavailable':(logging.WARNING,'private storage unavailable'),
    'render_internal_error':(logging.ERROR,'unexpected render error'),
    'lease_recovery':(logging.INFO,'expired claims recovered'),
    'claim_renewal_unavailable':(logging.WARNING,'claim renewal unavailable; original lease still enforced'),
    'queue_unavailable':(logging.WARNING,'durable queue unavailable; dispatch deferred'),
}
logger=logging.getLogger('nextphase.worker')


def emit(event,**fields):
    level,message=EVENTS[event]
    record={'schema_version':1,'timestamp':utcnow().isoformat(),'component':'worker',
            'event':event,'level':logging.getLevelName(level),'message':message}
    for name,value in fields.items():
        if name in ('job_id','worker_id'):
            if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError('Invalid event identity')
        elif name in ('output_seconds','wall_seconds'):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=172800:
                raise ValueError('Invalid event duration')
        elif name in ('requeued','failed'):
            if type(value) is not int or not 0<=value<=1000:raise ValueError('Invalid event count')
        elif name=='phase':
            if value not in PHASES:raise ValueError('Invalid worker phase')
        else:raise ValueError('Event field is not allowlisted')
        record[name]=value
    logger.log(level,json.dumps(record,separators=(',',':'),allow_nan=False))
