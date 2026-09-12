"""Promote one already packaged and canary-bound Lab candidate transactionally.

This worker deliberately does not build from, patch, or otherwise mutate the
running source tree.  Package production must first call ReleaseQueue.package_ready
and ReleaseQueue.accept_canary with evidence for the candidate.
"""
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lab_v1.release import ReleaseQueue
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy
from tools.build_current import CURRENT, activate_package, rollback_package
from tools.electron_lab_canary import run_canary


def main(sid, database):
    queue = ReleaseQueue(LabStore(database),
        policy=WorkforcePolicy(WorkforcePolicy.default_document()))
    folder = ROOT / 'artifacts/releases' / sid / 'activated'

    def monitor(_info):
        report = run_canary(CURRENT, folder, live=False)
        return report.get('status') == 'passed'

    try:
        result = queue.promote(sid, activate=activate_package,
                               monitor=monitor, rollback=rollback_package)
        return 0 if result['state'] == 'ACTIVE' else 2
    except Exception as exc:
        queue.update(sid, state='BLOCKED',
                     error=type(exc).__name__ + ': RELEASE_REQUIRES_RECONCILIATION')
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.session, args.database))
