"""Room <-> OpenCode file relay CLI (TASK_ID: ZARA-OPENCODE-SAFE-RELAY-002).

Commands:
  ingest  Append Room -> OpenCode TASK record(s) to inbox.jsonl.
  next    Read the next undelivered inbox task exactly once (--peek to look
          without marking it delivered).
  send    Append an OpenCode -> Room RESULT/BLOCKER/QUESTION to outbox.jsonl.
  status  Show pending/delivered/sent counts.

Safety: append-only JSONL, dedupe by message_id, content is never executed,
and an explicit EXECUTE marker in content is required before any write task
may be treated as authorized. This relay never reads .env, tokens, cookies,
passwords, browser profiles, or session data, and performs no browser
automation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.room_relay.relay_lib import OUTBOX_TYPES, RelayError, RelayStore  # noqa: E402

DEFAULT_STORE = Path(__file__).resolve().parent / "relay_store"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="relay", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="append Room->OpenCode TASK record(s) to inbox")
    p_ingest.add_argument("--store", default=DEFAULT_STORE)
    p_ingest.add_argument("--json", dest="json_text", metavar="RECORD", help="single record as JSON")
    p_ingest.add_argument("--file", metavar="JSONL", help="file with one record JSON per line")

    p_next = sub.add_parser("next", help="read the next undelivered inbox task once")
    p_next.add_argument("--store", default=DEFAULT_STORE)
    p_next.add_argument("--peek", action="store_true", help="look without marking delivered")

    p_send = sub.add_parser("send", help="append OpenCode->Room record to outbox")
    p_send.add_argument("--store", default=DEFAULT_STORE)
    p_send.add_argument("--type", required=True, choices=OUTBOX_TYPES)
    p_send.add_argument("--task-id", required=True)
    p_send.add_argument("--sender", required=True)
    p_send.add_argument("--recipient", required=True)
    p_send.add_argument("--content", required=True)
    p_send.add_argument("--message-id", default=None)

    p_status = sub.add_parser("status", help="show relay counts")
    p_status.add_argument("--store", default=DEFAULT_STORE)
    p_status.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def _load_records(args: argparse.Namespace) -> list[dict]:
    records: list[dict] = []
    if args.json_text:
        try:
            records.append(json.loads(args.json_text))
        except json.JSONDecodeError as exc:
            raise RelayError(f"Invalid --json: {exc}") from exc
    if args.file:
        path = Path(args.file)
        if not path.exists():
            raise RelayError(f"No such file: {path}")
        with path.open("r", encoding="utf-8-sig") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RelayError(f"{path}:{lineno}: invalid JSON line: {exc}") from exc
    if not records:
        raise RelayError("ingest requires --json or --file")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        store = RelayStore(args.store)
        if args.command == "ingest":
            for record in _load_records(args):
                stored = store.ingest(record)
                print(json.dumps(stored, ensure_ascii=False, sort_keys=True))
        elif args.command == "next":
            message = store.next_message(deliver=not args.peek)
            if message is None:
                print("NO_PENDING_TASK")
            else:
                print(json.dumps(message, ensure_ascii=False, sort_keys=True))
        elif args.command == "send":
            record = {
                "message_id": args.message_id,
                "sender": args.sender,
                "recipient": args.recipient,
                "task_id": args.task_id,
                "type": args.type,
                "content": args.content,
            }
            stored = store.send(record)
            print(json.dumps(stored, ensure_ascii=False, sort_keys=True))
        elif args.command == "status":
            status = store.status()
            if args.json:
                print(json.dumps(status, ensure_ascii=False, sort_keys=True))
            else:
                print(f"inbox_total: {status['inbox_total']}")
                print(f"inbox_pending: {status['inbox_pending']}")
                print(f"inbox_delivered: {status['inbox_delivered']}")
                print(f"outbox_total: {status['outbox_total']}")
        return 0
    except RelayError as exc:
        print(f"relay error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
