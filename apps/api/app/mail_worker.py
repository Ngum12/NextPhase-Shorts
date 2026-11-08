"""Separate bounded email dispatcher. Disabled configurations never send."""
import argparse
import json
import signal
import time
from sqlalchemy import select,func
from sqlalchemy.exc import SQLAlchemyError
from .db import engine,SessionLocal
from .migrate import require_current_schema
from .models import MailOutbox,MailBudget
from .mail_outbox import dispatch_one,cleanup_mail,real_enabled,reencrypt_pending


def report():
    with SessionLocal() as db:
        states=dict(db.execute(select(MailOutbox.state,func.count()).group_by(MailOutbox.state)).all())
        budget=db.get(MailBudget,'resend')
        return {'schema_version':1,'sending_enabled':real_enabled(),'states':states,
            'attempt_budget':None if budget is None else {'day':budget.day,'month':budget.month,
                'daily':budget.daily_attempts,'monthly':budget.monthly_attempts},
            'scope':'private operator report; provider acceptance is not inbox delivery'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true')
    parser.add_argument('--report',action='store_true');parser.add_argument('--reencrypt',action='store_true')
    parser.add_argument('--after',default='')
    parser.add_argument('--cleanup',action='store_true')
    args=parser.parse_args();require_current_schema(engine)
    if args.report:print(json.dumps(report(),indent=2));return
    if args.cleanup:print(json.dumps({'expired_candidates':cleanup_mail(),'batch_limit':1000}));return
    if args.reencrypt:
        print(json.dumps({**reencrypt_pending(args.after),'batch_limit':1000}));return
    if not real_enabled():print('Authentication email sending is disabled.');return
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    print('Authentication mail dispatcher started; message content is never logged.',flush=True)
    last_cleanup=0
    while not stopped:
        try:
            if time.monotonic()-last_cleanup>=30:cleanup_mail();last_cleanup=time.monotonic()
            dispatch_one()
        except SQLAlchemyError:
            print('Authentication mail database unavailable; retry deferred.',flush=True)
        if args.once:break
        time.sleep(1)


if __name__=='__main__':main()
