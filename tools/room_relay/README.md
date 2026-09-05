# Room <-> OpenCode File Relay (ZARA-OPENCODE-SAFE-RELAY-002)

Small, local, auditable, reversible file relay between the Room (Mentor) and
OpenCode. No network, no browser, no credentials.

## Layout

```
tools/room_relay/
  relay.py        CLI: ingest, next, send, status
  relay_lib.py    append-only JSONL core (RelayStore)
  watch.py        local ROOM_WORKER watcher (poll + audit + stop)
  relay_store/    runtime data (gitignored; created on first use)
    inbox.jsonl   Room -> OpenCode TASK records (append-only)
    outbox.jsonl  OpenCode -> Room RESULT/BLOCKER/QUESTION (append-only)
    state.json    delivered message_ids only; the one mutable artifact
    audit.jsonl   append-only watcher audit (event + message_id, never content)
```

Each record carries: `message_id`, `timestamp`, `sender`, `recipient`,
`task_id`, `type`, `content`, `status`. Inbox records additionally carry an
`authorization` tag: `EXECUTE` when content contains the literal `EXECUTE`
marker, otherwise `READ_ONLY`.

## Usage

```powershell
# Room -> OpenCode: append a task
python tools/room_relay/relay.py ingest --json '{"message_id":"t-1","sender":"room","recipient":"opencode","task_id":"T-1","type":"TASK","content":"EXECUTE inspect read-only"}'

# OpenCode: read the next undelivered task exactly once (--peek to look only)
python tools/room_relay/relay.py next
python tools/room_relay/relay.py next --peek

# OpenCode -> Room: post a result / blocker / question
python tools/room_relay/relay.py send --type RESULT --task-id T-1 --sender opencode --recipient room --content "done"

# Inspect
python tools/room_relay/relay.py status [--json]
```

All commands accept `--store <dir>` to override the default store.

## ROOM_WORKER watcher

```powershell
# One poll, then exit
python tools/room_relay/watch.py --once

# Continuous polling (Ctrl+C stops; audit trail in audit.jsonl)
python tools/room_relay/watch.py --interval 2

# Continuous polling that exits the moment the stop file exists
python tools/room_relay/watch.py --stop-file C:\Users\alexp\room-worker-stop.txt
```

The watcher only detects and audits NEW pending tasks. It never delivers
(delivery stays exclusive to `relay.py next`, preserving exactly-once), never
executes content, and never touches network, browser, cookies, or sessions.
The audit log records only events and message_ids — never task content.

## Safety invariants

- **Append-only**: `inbox.jsonl` / `outbox.jsonl` are never rewritten or
  truncated; history is never overwritten.
- **Dedupe by `message_id`**: a duplicate id (inbox or outbox) is rejected.
- **Never executes content**: received content is data only. The relay and
  CLI contain no eval, exec, subprocess, action dispatch, URL handling, or
  browser automation.
- **Explicit authorization**: an inbox task is tagged `READ_ONLY` unless its
  content contains the literal `EXECUTE` marker. Only `EXECUTE`-tagged tasks
  may be treated as write tasks, and that decision belongs to the executor —
  the relay never treats content as an action.
- **Reversible**: deleting `state.json` returns all inbox records to PENDING;
  history files are never altered.
- **No secrets**: this relay never reads or writes `.env`, tokens, cookies,
  passwords, browser profiles, or session stores.

## Tests

```powershell
python -m pytest tests/test_room_relay.py -v
```
