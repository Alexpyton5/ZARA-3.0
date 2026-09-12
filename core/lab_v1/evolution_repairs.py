"""Reviewed repair catalog. Models select a repair; they cannot inject executable code."""
import hashlib

REPAIR_ID = 'memory-promotion-dedup-v1'
RELATIVE_PATH = 'memory/user_memory.py'
BEFORE = '''            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO user_facts (id, category, fact, confidence, status, source, ref, "'''
AFTER = '''            with self._connect() as conn:
                # Serialize Lab promotion across processes, including crash/replay before outbox acknowledgement.
                conn.execute("BEGIN IMMEDIATE")
                if source == "zara_lab" and ref:
                    existing = conn.execute(
                        "SELECT * FROM user_facts WHERE source='zara_lab' AND ref=? ORDER BY created_at LIMIT 1",
                        (ref,),
                    ).fetchone()
                    if existing is not None:
                        return dict(existing)
                conn.execute(
                    "INSERT INTO user_facts (id, category, fact, confidence, status, source, ref, "'''


def candidate(source):
    newline = '\r\n' if '\r\n' in source else '\n'
    source = source.replace('\r\n', '\n')
    if source.count(BEFORE) != 1 or AFTER in source:
        raise ValueError('Repair precondition no longer matches')
    return source.replace(BEFORE, AFTER, 1).replace('\n', newline)


def reverse_candidate(source):
    newline = '\r\n' if '\r\n' in source else '\n'
    source = source.replace('\r\n', '\n')
    if source.count(AFTER) != 1: raise ValueError('Repair postcondition no longer matches')
    return source.replace(AFTER, BEFORE, 1).replace('\n', newline)


def validate_change(path, before, after, authorization_ref):
    if path.name != 'user_memory.py': return False
    try:
        if authorization_ref == 'evolution:' + REPAIR_ID:
            return candidate(before) == after
        if authorization_ref == 'evolution:rollback:' + REPAIR_ID:
            return candidate(after) == before
    except ValueError:
        pass
    return False


def digest(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()
