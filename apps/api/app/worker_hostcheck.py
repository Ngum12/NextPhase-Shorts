"""Probe actual worker cgroup and decoder isolation, without rendering customer data."""
import json
from .worker_limits import require_worker_limits,require_unprivileged
from .render_sandbox import require_support


def main():
    result={'schema_version':1}
    for name,check in (('unprivileged_user',require_unprivileged),('cgroup_limits',require_worker_limits),('filesystem_and_network_isolation',require_support)):
        try:check();result[name]='enforced'
        except (RuntimeError,OSError):result[name]='unsupported_or_unenforced'
    result['ready']=all(value=='enforced' for key,value in result.items() if key!='schema_version')
    result['scope']='this process and kernel only; not production load/security certification'
    print(json.dumps(result,indent=2))
    if not result['ready']:raise SystemExit(1)


if __name__=='__main__':main()
