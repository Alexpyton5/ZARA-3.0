"""Local, reversible FILE_RELAY watcher for ROOM_WORKER mode.

Polls the relay store for NEW undelivered inbox tasks and appends an
append-only audit trail. It NEVER delivers messages (delivery stays
exclusive to ``relay.py next``, keeping exactly-once semantics), never
executes content, and never touches the network, browser, cookies, or
sessions.

Stop mechanisms (all leave no state behind beyond the audit log):
  * Ctrl+C
  * --once           run a single poll, then exit
  * --stop-file F    exit as soon as file F exists (create it to stop)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.room_relay.relay_lib import RelayStore  # noqa: E402

DEFAULT_STORE = Path(__file__).resolve().parent / "relay_store"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="room-worker", description=__doc__)
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds")
    parser.add_argument("--once", action="store_true", help="single poll, then exit")
    parser.add_argument("--stop-file", metavar="FILE", help="exit as soon as this file exists")
    return parser


def _notify(store: RelayStore, event: str, detail: str = "") -> None:
    store.audit(f"watcher:{event}", detail)
    suffix = f" {detail}" if detail else ""
    print(f"AUDIT watcher:{event}{suffix}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    store = RelayStore(args.store)
    stop_path = Path(args.stop_file) if args.stop_file else None
    _notify(store, "start", str(store.dir))
    try:
        while True:
            for record in store.pending_records():
                message_id = str(record["message_id"])
                _notify(store, "found", message_id)
                print(f"NEW_TASK {message_id}")
            if args.once:
                _notify(store, "once_done")
                return 0
            if stop_path is not None and stop_path.exists():
                _notify(store, "stop_file", str(stop_path))
                return 0
            time.sleep(max(0.0, args.interval))
    except KeyboardInterrupt:
        _notify(store, "keyboard_interrupt")
        return 0


if __name__ == "__main__":
    sys.exit(main())
