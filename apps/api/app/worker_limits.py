"""Fail closed if the Compose worker's required cgroup v2 limits are absent."""
from pathlib import Path
import sys


def require_worker_limits(root=Path('/sys/fs/cgroup')):
    try:
        if not sys.platform.startswith('linux'):raise ValueError('Linux required')
        memory=int((root/'memory.max').read_text().strip())
        pids=int((root/'pids.max').read_text().strip())
        quota,period=map(int,(root/'cpu.max').read_text().split())
        if not (0<memory<=2147483648 and 0<pids<=128 and period>0 and 0<quota<=2*period):
            raise ValueError('Unbounded worker cgroup')
    except (OSError,ValueError):
        raise RuntimeError('Worker requires enforced cgroup v2 limits: memory <=2 GiB, CPU <=2, PIDs <=128') from None
