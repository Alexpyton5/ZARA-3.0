"""Durable gates for candidate package, canary, activation, monitor and rollback."""
from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager, nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import time

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

from core.lab_v1.evolution import WORKFLOW
from core.lab_v1.evolution_repairs import REPAIR_ID, digest
from core.lab_v1.workforce_policy import WorkforcePolicy

SOURCE_WORKFLOW = 'source_mission'


def _same_digest(actual, expected):
    """Official build metadata uses uppercase hex; hashlib returns lowercase."""
    return (isinstance(actual, str) and isinstance(expected, str)
            and len(actual) == len(expected) == 64
            and all(char in '0123456789abcdef' for char in actual.lower())
            and all(char in '0123456789abcdef' for char in expected.lower())
            and actual.lower() == expected.lower())


@contextmanager
def _promotion_lock(build):
    """Serialize Lab source promotion across processes; OS unlocks on crash."""
    path = Path(build.ROOT) / 'artifacts' / 'releases' / 'lab-source-promotion.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('SOURCE_PROMOTION_ALREADY_IN_PROGRESS') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class ReleaseQueue:
    TERMINAL = frozenset({'ACTIVE', 'ROLLED_BACK', 'BLOCKED'})

    def __init__(self, store, *, policy=None, build=None):
        self.store = store
        self.policy = policy or WorkforcePolicy(WorkforcePolicy.default_document())
        self.build = build
        with store._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS lab_releases('
                         'session_id TEXT PRIMARY KEY, document TEXT NOT NULL)')

    def snapshot(self, sid=None):
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM lab_releases ' +
                ('WHERE session_id=?' if sid else 'ORDER BY rowid DESC LIMIT 1'),
                (sid,) if sid else ()).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, sid, **changes):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT document FROM lab_releases WHERE session_id=?', (sid,)).fetchone()
            doc = json.loads(row[0]) if row else {'session_id': sid, 'created_at': time.time()}
            doc.update(changes, updated_at=time.time())
            conn.execute('INSERT OR REPLACE INTO lab_releases VALUES(?,?)', (sid, json.dumps(doc)))
        return doc

    def schedule(self, evolution, workspace):
        """Reserve a release; scheduling never starts a legacy build or edits CURRENT."""
        sid = evolution['session_id']
        existing = self.snapshot(sid)
        if existing:
            return existing
        mission = self.store.mission_snapshot(sid)
        if (not self.policy.background_enabled or evolution.get('workflow') != WORKFLOW
                or evolution.get('repair_id') != REPAIR_ID
                or evolution.get('state') != 'CANDIDATE_VERIFIED'
                or evolution.get('build_state') != 'PACKAGE_PENDING'
                or not mission or mission['state'] != 'COMPLETED'):
            raise ValueError('Release requires a governed verified candidate')
        root = Path(workspace).resolve(strict=True)
        source = Path(evolution['source']).resolve(strict=True)
        candidate = Path(evolution['candidate']).resolve(strict=True)
        baseline = Path(evolution['baseline']).resolve(strict=True)
        if root not in source.parents:
            raise ValueError('Source is outside the configured workspace')
        if root in candidate.parents or root in baseline.parents:
            raise ValueError('Candidate and baseline must be outside production workspace')
        if (digest(source.read_text(encoding='utf-8')) != evolution['before_sha256']
                or digest(baseline.read_text(encoding='utf-8')) != evolution['before_sha256']
                or digest(candidate.read_text(encoding='utf-8')) != evolution['after_sha256']):
            raise ValueError('Candidate or production baseline changed before packaging')
        return self.update(sid, state='PACKAGE_PENDING', workflow=WORKFLOW, repair_id=REPAIR_ID,
            candidate=str(candidate), candidate_sha256=evolution['after_sha256'],
            baseline_sha256=evolution['before_sha256'], current_preserved=True)

    def schedule_source_candidate(self, sid, receipt, workspace):
        """Queue a verified SourceMission candidate on the same durable gates.

        No package, pointer or source byte is touched here; scheduling only
        records that the candidate satisfies every promotion precondition.
        """
        existing = self.snapshot(sid)
        if existing:
            return existing
        readiness = promotion_readiness(receipt, workspace, self.build)
        if not readiness['eligible']:
            raise ValueError('Release requires a promotable candidate: ' + readiness['reason'])
        return self.update(sid, state='PACKAGE_PENDING', workflow=SOURCE_WORKFLOW,
            candidate=str(Path(receipt['package']).resolve()),
            candidate_source_sha256=receipt['source_sha256'],
            receipt=receipt, workspace=str(Path(workspace).resolve()),
            readiness=readiness, current_preserved=True)

    def package_ready(self, sid, package, package_info):
        doc = self.snapshot(sid)
        if not doc or doc.get('state') != 'PACKAGE_PENDING':
            raise ValueError('Package gate is not ready')
        package = Path(package).resolve(strict=True)
        required = ('BUILD_ID', 'SOURCE_SHA256', 'ASAR_SHA256', 'BACKEND_SHA256')
        if any(not package_info.get(key) for key in required):
            raise ValueError('Package identity is incomplete')
        if doc.get('workflow') == SOURCE_WORKFLOW:
            if (str(package) != doc.get('candidate')
                    or package_info['BUILD_ID'] != doc['receipt'].get('build_id')
                    or package_info['SOURCE_SHA256'] != doc['candidate_source_sha256']
                    or not _same_digest(package_info['ASAR_SHA256'], doc['receipt'].get('asar_sha256'))
                    or not _same_digest(package_info['BACKEND_SHA256'], doc['receipt'].get('backend_sha256'))):
                raise ValueError('Queued package differs from the verified candidate')
        return self.update(sid, state='CANARY_PENDING', package=str(package),
            build_id=package_info['BUILD_ID'], package_source_sha256=package_info['SOURCE_SHA256'],
            asar_sha256=package_info['ASAR_SHA256'], backend_sha256=package_info['BACKEND_SHA256'])

    def accept_canary(self, sid, validation):
        doc = self.snapshot(sid)
        if not doc or doc.get('state') != 'CANARY_PENDING':
            raise ValueError('Canary gate is not ready')
        validation = Path(validation).resolve(strict=True)
        report = json.loads(validation.read_text(encoding='utf-8'))
        if (report.get('status') != 'passed'
                or not _same_digest(report.get('asar_sha256'), doc['asar_sha256'])
                or not _same_digest(report.get('backend_sha256'), doc['backend_sha256'])
                or (doc.get('workflow') == SOURCE_WORKFLOW
                    and str(validation) != str(Path(doc['receipt']['canary_report']).resolve()))):
            raise ValueError('Canary does not identify the queued package')
        return self.update(sid, state='READY_TO_ACTIVATE', validation=str(validation),
                           canary_accepted_at=time.time())

    def promote(self, sid, *, activate, monitor, rollback, commit=None):
        """Activate once; a failed post-activation monitor rolls back immediately."""
        doc = self.snapshot(sid)
        if not doc or doc.get('state') != 'READY_TO_ACTIVATE':
            raise ValueError('Activation gate is not ready')
        source = doc.get('workflow') == SOURCE_WORKFLOW
        build = _build_module(self.build, doc.get('workspace')) if source else None
        with _promotion_lock(build) if source else nullcontext():
            doc = self.snapshot(sid)
            if not doc or doc.get('state') != 'READY_TO_ACTIVATE':
                raise ValueError('Activation gate is not ready')
            if source:
                if commit is None or not isinstance(getattr(activate, '__self__', None), SourcePromotion):
                    raise ValueError('SOURCE_PROMOTION_REQUIRES_DURABLE_COMMIT')
                promotion = activate.__self__
                if (promotion.workspace != Path(doc['workspace'])
                        or promotion.receipt != doc['receipt']
                        or str(Path(doc['package']).resolve()) != doc['candidate']
                        or str(Path(doc['validation']).resolve()) != str(Path(doc['receipt']['canary_report']).resolve())):
                    raise ValueError('SOURCE_PROMOTION_QUEUE_RECEIPT_MISMATCH')
                readiness = promotion_readiness(doc['receipt'], doc['workspace'], build)
                if not readiness['eligible']:
                    raise ValueError('SOURCE_PROMOTION_NO_LONGER_READY: ' + readiness['reason'])
            return self._promote_locked(sid, doc, activate, monitor, rollback, commit)

    def _promote_locked(self, sid, doc, activate, monitor, rollback, commit):
        self.update(sid, state='ACTIVATING')
        try:
            info = activate(Path(doc['package']), Path(doc['validation']))
        except Exception as exc:
            if doc.get('workflow') == SOURCE_WORKFLOW:
                self.update(sid, state='ACTIVATING',
                            error=type(exc).__name__ + ': ACTIVATION_NEEDS_RECONCILIATION')
            else:
                self.update(sid, state='BLOCKED', error=type(exc).__name__ + ': ACTIVATION_RESTORED')
            raise
        journal = Path(info['ROLLBACK_JOURNAL'])
        self.update(sid, state='MONITORING', rollback_journal=str(journal),
                    active_build_id=info['BUILD_ID'], package=info.get('package', doc.get('package')))
        try:
            healthy = monitor(info)
        except Exception:
            healthy = False
        if healthy is not True:
            try:
                rollback(journal)
            except Exception as exc:
                self.update(sid, state='BLOCKED', needs_owner=True,
                            error=type(exc).__name__ + ': POST_ACTIVATION_ROLLBACK_FAILED')
                raise
            return self.update(sid, state='ROLLED_BACK', error='POST_ACTIVATION_MONITOR_FAILED',
                               current_preserved=True)
        if commit is not None:
            try:
                commit(info)
            except Exception as exc:
                self.update(sid, state='COMMIT_PENDING',
                            error=type(exc).__name__ + ': COMMIT_NEEDS_RECONCILIATION')
                raise
        with self.store._connect() as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lab_evolution'").fetchone()
            row = conn.execute('SELECT document FROM lab_evolution WHERE session_id=?', (sid,)).fetchone() if exists else None
            if row:
                evolution = json.loads(row[0]); evolution.update(build_state='ACTIVE',
                    build_id=info['BUILD_ID'], learned_outcome='PROMOTION_MONITORED_PASS')
                conn.execute('UPDATE lab_evolution SET document=? WHERE session_id=?',
                             (json.dumps(evolution), sid))
        return self.update(sid, state='ACTIVE', build_id=info['BUILD_ID'], monitored=True)

    def reconcile_interrupted(self, sid):
        """Map one interrupted queue row to a proven journal outcome, idempotently."""
        doc = self.snapshot(sid)
        if not doc or doc.get('workflow') != SOURCE_WORKFLOW:
            return doc
        if doc.get('state') not in {'ACTIVATING', 'MONITORING', 'COMMIT_PENDING'}:
            return doc
        build = _build_module(self.build, doc.get('workspace'))
        with _promotion_lock(build):
            doc = self.snapshot(sid)
            if doc.get('state') not in {'ACTIVATING', 'MONITORING', 'COMMIT_PENDING'}:
                return doc
            matches = []
            for path in _promotion_journals(build):
                try:
                    journal = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    continue
                if journal.get('candidate_package_source') == doc.get('candidate'):
                    matches.append(path)
            if len(matches) != 1:
                return self.update(sid, state='BLOCKED', needs_owner=True,
                                   error='PROMOTION_JOURNAL_NOT_UNIQUE_OR_MISSING')
            promotion = SourcePromotion.from_journal(matches[0], build=build)
            if promotion.journal['state'] not in TERMINAL_PROMOTION_STATES:
                promotion.reconcile()
            journal = promotion.journal
            if journal['state'] in {'COMMITTED', 'RECONCILED_COMMITTED'}:
                if not promotion._verified_candidate(journal.get('new_build_id')):
                    return self.update(sid, state='BLOCKED', needs_owner=True,
                                       error='COMMITTED_CANDIDATE_NO_LONGER_VERIFIED')
                return self.update(sid, state='ACTIVE', monitored=True,
                                   build_id=journal['new_build_id'], rollback_journal=str(matches[0]),
                                   package=journal.get('candidate_package'))
            if journal['state'] in {'ROLLED_BACK', 'RECONCILED_KNOWN_GOOD', 'ACTIVATION_FAILED_RESTORED'}:
                evidence = promotion_evidence(journal, build)
                if evidence['coherent_state'] == 'KNOWN_GOOD':
                    return self.update(sid, state='ROLLED_BACK', current_preserved=True,
                                       rollback_journal=str(matches[0]))
            return self.update(sid, state='BLOCKED', needs_owner=True,
                               error='PROMOTION_RECONCILIATION_NEEDS_OWNER',
                               rollback_journal=str(matches[0]))


def _build_module_for_workspace(workspace):
    """Load build operations from the exact source checkout the Lab targets."""
    root = Path(workspace).resolve(strict=True)
    source = root / 'tools' / 'build_current.py'
    if not source.is_file() or not (root / 'tools' / 'build_candidate.py').is_file():
        raise ValueError('BUILD_TOOLS_MISSING_FROM_TARGET_WORKSPACE')
    name = '_zara_lab_build_current_' + hashlib.sha256(str(root).encode()).hexdigest()[:16]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, source)
        if spec is None or spec.loader is None:
            raise ValueError('TARGET_BUILD_TOOLS_CANNOT_LOAD')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    if Path(module.ROOT).resolve() != root:
        raise ValueError('TARGET_BUILD_ROOT_MISMATCH')
    return module


def _build_module(build=None, workspace=None):
    if build is not None:
        return build
    if workspace is not None:
        return _build_module_for_workspace(workspace)
    from tools import build_current
    return build_current


def _file_digest(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _safe_lab_overlay_path(value):
    """Return a canonical in-scope relative path, rejecting traversal early."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError('CANDIDATE_OVERLAY_PATH_INVALID')
    normalized = value.replace('\\', '/')
    relative = PurePosixPath(normalized)
    if (relative.is_absolute() or ':' in normalized
            or relative.as_posix() != normalized
            or any(part in ('', '.', '..') for part in relative.parts)):
        raise ValueError('CANDIDATE_OVERLAY_PATH_INVALID')
    path = Path(*relative.parts)
    if not (normalized.startswith('core/lab_v1/')
            or normalized.startswith('tests/test_lab_')
            or normalized == 'tests/test_zara_mission_regression.py'):
        raise ValueError('CANDIDATE_OUTSIDE_LAB_SCOPE')
    return path


def _reject_symlinked_path(root, relative):
    """Do not let a candidate follow a link outside its source/sandbox tree."""
    root = Path(root).resolve(strict=True)
    target = root.joinpath(*Path(relative).parts)
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError('CANDIDATE_OVERLAY_PATH_ESCAPES_ROOT') from exc
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('CANDIDATE_OVERLAY_SYMLINK_FORBIDDEN')
    return target


def known_good(build=None):
    """Identity of the exact package named by the active-build pointer."""
    build = _build_module(build)
    try:
        pointer_path = Path(build.ROOT) / 'ZARA_ACTIVE_BUILD.json'
        pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
        exe = Path(pointer['EXE_PATH']).resolve(strict=True)
        current = exe.parent.parent
        current.relative_to((Path(build.ROOT) / 'frontend').resolve())
        if exe != build.packaged_paths(current)['EXE_SHA256'].resolve(strict=True):
            raise ValueError('ACTIVE_EXE_PATH_MISMATCH')
        info_path = current / 'win-unpacked' / 'BUILD_INFO.json'
        info = json.loads(info_path.read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {'available': False, 'reason': 'ACTIVE_BUILD_INFO_UNREADABLE'}
    artifacts = {key: _file_digest(path) for key, path in build.packaged_paths(current).items()}
    if (any(pointer.get(key) != info.get(key) for key in ('BUILD_ID', 'EXE_PATH'))
            or any(not _same_digest(pointer.get(key), info.get(key)) for key in artifacts)
            or any(not _same_digest(artifacts[key], info.get(key)) for key in artifacts)):
        return {'available': False, 'reason': 'ACTIVE_ARTIFACTS_DO_NOT_MATCH_BUILD_INFO',
                'build_id': info.get('BUILD_ID'), 'artifacts': artifacts}
    return {'available': True, 'build_id': info.get('BUILD_ID'), 'path': str(current),
            'artifacts': artifacts,
            'pointers': {name: _file_digest(Path(build.ROOT) / name)
                         for name in ('ZARA_ACTIVE_BUILD.json', 'ZARA_ACTIVE_BUILD.txt')}}


def promotion_readiness(receipt, workspace, build=None):
    """Decide, without mutating anything, whether this candidate may be promoted."""
    workspace = Path(workspace).resolve()
    build = _build_module(build, workspace)

    def refuse(reason, **extra):
        return dict({'eligible': False, 'reason': reason, 'checked_at': time.time()}, **extra)

    if not isinstance(receipt, dict):
        return refuse('CANDIDATE_RECEIPT_INVALID')
    if workspace != Path(build.ROOT).resolve():
        # Readiness is only meaningful for the workspace whose CURRENT package
        # and pointers would actually be swapped; never inspect another tree.
        return refuse('WORKSPACE_IS_NOT_THE_CANONICAL_BUILD_ROOT')
    review = receipt.get('review_evidence')
    canary = receipt.get('canary')
    if (receipt.get('status') != 'PACKAGED_RUNTIME_CANDIDATE'
            or receipt.get('candidate_status') != 'VERIFIED_AWAITING_APPROVAL'
            or receipt.get('desktop_package') is not True):
        return refuse('CANDIDATE_NOT_VERIFIED')
    if not isinstance(review, dict) or review.get('verdict') != 'PASS':
        return refuse('INDEPENDENT_REVIEW_NOT_PASSED')
    if receipt.get('risk') != 'LOW':
        return refuse('CANDIDATE_RISK_NOT_LOW')
    if (not isinstance(canary, dict) or canary.get('status') != 'passed'
            or canary.get('live') is not False or canary.get('runs', []) != []):
        return refuse('PACKAGED_CANARY_NOT_PASSED')
    staged_value = receipt.get('workspace')
    package_value = receipt.get('package')
    if not isinstance(staged_value, str) or not isinstance(package_value, str):
        return refuse('CANDIDATE_PACKAGE_INVALID')
    try:
        staged = Path(staged_value).resolve(strict=True)
        package = Path(package_value).resolve(strict=True)
        package.relative_to(staged / 'frontend')
        if staged == workspace or workspace in staged.parents:
            return refuse('CANDIDATE_WORKSPACE_NOT_ISOLATED')
        paths = build.packaged_paths(package)
        info = json.loads((package / 'win-unpacked' / 'BUILD_INFO.json').read_text(encoding='utf-8'))
        manifest = json.loads((package / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return refuse('CANDIDATE_PACKAGE_INVALID')
    if (not isinstance(info, dict) or not isinstance(manifest, dict)
            or not isinstance(receipt.get('build_id'), str)
            or receipt['build_id'] != info.get('BUILD_ID')
            or receipt['build_id'] not in package.name
            or info.get('SOURCE_SHA256') != receipt.get('source_sha256')
            or manifest.get('sha256') != receipt.get('source_sha256')):
        return refuse('CANDIDATE_PACKAGE_IDENTITY_MISMATCH')
    builder_path = staged / 'tools' / 'build_candidate.py'
    builder = manifest.get('build_tool')
    if (not isinstance(builder, dict) or builder.get('path') != 'tools/build_candidate.py'
            or not _same_digest(_file_digest(builder_path), builder.get('sha256'))
            or not _same_digest(info.get('BUILD_TOOL_SHA256'), builder.get('sha256'))
            or not _same_digest(receipt.get('build_tool_sha256'), builder.get('sha256'))):
        return refuse('CANDIDATE_BUILD_TOOL_IDENTITY_MISMATCH')
    build_receipt_value = receipt.get('build_receipt')
    if not isinstance(build_receipt_value, str):
        return refuse('CANDIDATE_BUILD_RECEIPT_MISSING')
    try:
        build_receipt_path = Path(build_receipt_value).resolve(strict=True)
        build_receipt_path.parent.parent.relative_to(staged.parent)
        build_receipt = json.loads(build_receipt_path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return refuse('CANDIDATE_BUILD_RECEIPT_MISSING')
    if (build_receipt_path.parent.parent != staged.parent
            or not build_receipt_path.parent.name.startswith('desktop-build-evidence')
            or build_receipt.get('timeout') is not False
            or build_receipt.get('exit_code') != 0):
        return refuse('CANDIDATE_BUILD_NOT_COMPLETED')
    report_value = receipt.get('canary_report')
    if not isinstance(report_value, str):
        return refuse('CANARY_REPORT_MISSING')
    report_path = Path(report_value)
    try:
        if (report_path.resolve(strict=True).name != 'VALIDATION.json'
                or report_path.resolve(strict=True).parent.parent != staged.parent
                or json.loads(report_path.read_text(encoding='utf-8')) != canary):
            return refuse('CANARY_REPORT_DOES_NOT_MATCH_RECEIPT')
    except (OSError, json.JSONDecodeError):
        return refuse('CANARY_REPORT_MISSING')
    identity = {}
    for key in ('exe', 'asar', 'backend'):
        metadata_key = key.upper() + '_SHA256'
        named_path = receipt.get(key + '_path')
        if not isinstance(named_path, str):
            return refuse('CANDIDATE_ARTIFACT_PATH_MISMATCH', artifact=key)
        try:
            actual_path = Path(named_path).resolve(strict=True)
            expected_path = paths[metadata_key].resolve(strict=True)
        except (OSError, ValueError, KeyError):
            return refuse('CANDIDATE_ARTIFACT_PATH_MISMATCH', artifact=key)
        if actual_path != expected_path:
            return refuse('CANDIDATE_ARTIFACT_PATH_MISMATCH', artifact=key)
        actual = _file_digest(actual_path)
        if (not _same_digest(actual, receipt.get(key + '_sha256'))
                or not _same_digest(actual, info.get(metadata_key))):
            return refuse('CANDIDATE_ARTIFACT_DRIFT', artifact=key)
        identity[key + '_sha256'] = actual
    if (not isinstance(info.get('EXE_PATH'), str)
            or Path(info['EXE_PATH']).resolve() != paths['EXE_SHA256'].resolve()
            or not _same_digest(canary.get('asar_sha256'), identity['asar_sha256'])
            or not _same_digest(canary.get('backend_sha256'), identity['backend_sha256'])):
        return refuse('CANDIDATE_CANARY_PACKAGE_MISMATCH')
    overlay = receipt.get('overlay')
    if not isinstance(overlay, list) or not overlay or not staged.is_dir():
        return refuse('CANDIDATE_OVERLAY_UNAVAILABLE')
    if any(not isinstance(item, dict) for item in overlay):
        return refuse('CANDIDATE_OVERLAY_INVALID')
    files = manifest.get('files')
    if (not isinstance(files, list) or any(not isinstance(item, dict)
            or not isinstance(item.get('path'), str)
            or not isinstance(item.get('sha256'), str) for item in files)):
        return refuse('CANDIDATE_SOURCE_MANIFEST_INVALID')
    manifested = {item.get('path'): item.get('sha256') for item in files}
    if len(manifested) != len(files):
        return refuse('CANDIDATE_SOURCE_MANIFEST_INVALID')
    for item in overlay:
        try:
            relative = _safe_lab_overlay_path(item.get('path'))
            overlay_path = _reject_symlinked_path(staged, relative)
        except ValueError as exc:
            return refuse(str(exc), path=item.get('path'))
        if _file_digest(overlay_path) != item.get('sha256'):
            return refuse('CANDIDATE_OVERLAY_DRIFT', path=item.get('path'))
        if not _same_digest(manifested.get(relative.as_posix()), item.get('sha256')):
            return refuse('CANDIDATE_OVERLAY_NOT_IN_SOURCE_MANIFEST', path=item.get('path'))
    baseline = known_good(build)
    if not baseline.get('available'):
        return refuse('ROLLBACK_TARGET_UNAVAILABLE', known_good=baseline)
    pending = pending_promotions(build)
    if pending:
        # A crashed promotion owns the runtime until it is reconciled; starting a
        # second one on top of it is exactly how a hybrid state is created. A
        # reconciliation that already failed is worse: only the owner clears it.
        return refuse('PROMOTION_RECONCILIATION_NEEDS_OWNER'
                      if any(item.get('needs_owner') for item in pending)
                      else 'PROMOTION_RECONCILIATION_PENDING', pending=pending)
    if not isinstance(receipt.get('source_sha256'), str) or not receipt['source_sha256']:
        return refuse('CANDIDATE_SOURCE_IDENTITY_MISSING')
    return {'eligible': True, 'reason': 'PROMOTABLE', 'checked_at': time.time(),
            'workspace': str(workspace), 'candidate_build_id': receipt.get('build_id'),
            'candidate_source_sha256': receipt['source_sha256'], 'candidate_identity': identity,
            'known_good': baseline}


#: A journal in any of these states is *resolved*: the promotion reached one
#: single coherent state and said so durably. Nothing is pending on it.
RESOLVED_PROMOTION_STATES = frozenset({
    'COMMITTED', 'ROLLED_BACK', 'ACTIVATION_FAILED_RESTORED',
    'RECONCILED_KNOWN_GOOD', 'RECONCILED_COMMITTED'})

#: Reconciliation ran, could not prove a single coherent state, and stopped.
#: This is an unresolved failure awaiting a human, not a conclusion. It is
#: final only for the *machine*: no automatic reconciliation may retry the
#: uncertain effect, and it never stops being pending on its own — not by
#: expiry, not by a later boot, only when the owner resolves the journal.
OWNER_RESOLUTION_REQUIRED_STATES = frozenset({'RECONCILIATION_NEEDS_OWNER'})

#: States where automatic reconciliation must not act again (`reconcile`).
#: Not the same question as "is anything pending" — see `pending_promotions`.
TERMINAL_PROMOTION_STATES = RESOLVED_PROMOTION_STATES | OWNER_RESOLUTION_REQUIRED_STATES


def _pointer_build_id(build):
    try:
        document = json.loads((Path(build.ROOT) / 'ZARA_ACTIVE_BUILD.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return document.get('BUILD_ID') if isinstance(document, dict) else None


def _classify(observed, good, candidate):
    if observed is not None and observed == good:
        return 'KNOWN_GOOD'
    if observed is not None and candidate is not None and observed == candidate:
        return 'CANDIDATE'
    return 'UNKNOWN'


def promotion_evidence(journal, build=None):
    """Read the four layers from disk; never trust what the journal claims.

    Source tree, sidecar binary, active package and the runtime pointer are each
    classified against the two identities the journal recorded before touching
    anything. Only a unanimous verdict counts as a coherent state.
    """
    build = _build_module(build)
    baseline = known_good(build)
    good_id = (journal.get('known_good') or {}).get('build_id')
    candidate_id = journal.get('new_build_id')
    sidecar = journal.get('sidecar') or {}
    layers = {
        'source': {'observed': build.source_identity()['sha256'],
                   'known_good': journal.get('before_source_sha256'),
                   'candidate': journal.get('candidate_source_sha256')},
        'sidecar': {'observed': _file_digest(sidecar.get('path', '')),
                    'known_good': sidecar.get('before_sha256'),
                    'candidate': journal.get('candidate_backend_sha256')},
        'package': {'observed': baseline.get('build_id') if baseline.get('available') else None,
                    'known_good': good_id, 'candidate': candidate_id},
        'pointer': {'observed': _pointer_build_id(build), 'known_good': good_id,
                    'candidate': candidate_id},
    }
    for layer in layers.values():
        layer['verdict'] = _classify(layer['observed'], layer['known_good'], layer['candidate'])
    verdicts = {name: layer['verdict'] for name, layer in layers.items()}
    unique = set(verdicts.values())
    coherent = ('KNOWN_GOOD' if unique == {'KNOWN_GOOD'}
                else 'CANDIDATE' if unique == {'CANDIDATE'} else 'MIXED')
    return {'layers': layers, 'verdicts': verdicts, 'coherent_state': coherent,
            'package_available': bool(baseline.get('available')),
            'observed_at': time.time()}


def _build_journal_for(build, staged_package):
    """Locate the canonical build_current journal produced for this staging dir."""
    folder = Path(build.ROOT) / 'artifacts' / 'releases'
    if not staged_package or not folder.is_dir():
        return None
    for path in sorted(folder.glob('*.json')):
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(document, dict) and document.get('candidate') == str(staged_package):
            return path, document
    return None


class SourcePromotion:
    """Promote source + packaged runtime as one reversible unit.

    ``activate`` writes the complete new state (source, sidecar, staged package)
    and only then hands the pointer swap to the canonical
    ``build_current.activate_package``. Any failure — including a failed
    post-activation health check — restores source, sidecar, package and
    pointers from one journal, never a mixture of two builds.
    """

    def __init__(self, workspace, receipt, *, build=None):
        self.workspace = Path(workspace).resolve()
        self.build = _build_module(build, self.workspace)
        self.receipt = receipt
        self.staged = Path(receipt['workspace'])
        self.journal_path = None
        self.journal = None

    # -- source layer ----------------------------------------------------
    def _plan_source(self, backup_dir):
        """Back up every target and describe the whole write before writing any.

        The returned entries are journalled first, so a crash in the middle of
        the write still leaves a complete undo description on disk.
        """
        entries = []
        backup_dir.mkdir(parents=True, exist_ok=True)
        for item in self.receipt['overlay']:
            relative = _safe_lab_overlay_path(item['path'])
            target = _reject_symlinked_path(self.workspace, relative)
            origin = _reject_symlinked_path(self.staged, relative)
            if _file_digest(origin) != item['sha256']:
                raise ValueError('CANDIDATE_OVERLAY_DRIFT: ' + item['path'])
            before = _file_digest(target)
            if before is not None:
                saved = backup_dir.joinpath(*relative.parts)
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            entries.append({'path': relative.as_posix(), 'before_sha256': before,
                            'after_sha256': item['sha256']})
        return entries

    def _apply_source(self, entries):
        for entry in entries:
            relative = Path(entry['path'])
            target = _reject_symlinked_path(self.workspace, relative)
            origin = _reject_symlinked_path(self.staged, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
            if _file_digest(target) != entry['after_sha256']:
                raise ValueError('PROMOTED_SOURCE_HASH_MISMATCH: ' + entry['path'])

    def _check_restore_source(self, journal):
        """Refuse rollback if user edits drifted or a needed backup is absent."""
        backup_dir = Path(journal['source_backup'])
        if backup_dir != self.journal_path.parent / 'source-backup':
            raise ValueError('SOURCE_BACKUP_PATH_MISMATCH')
        for entry in journal['source_entries']:
            relative = _safe_lab_overlay_path(entry['path'])
            target = _reject_symlinked_path(self.workspace, relative)
            current = _file_digest(target)
            before, candidate = entry['before_sha256'], entry['after_sha256']
            if current != before and current != candidate:
                raise ValueError('SOURCE_DRIFT_AFTER_PROMOTION: ' + entry['path'])
            if before is not None and current != before:
                if _file_digest(backup_dir.joinpath(*relative.parts)) != before:
                    raise ValueError('SOURCE_BACKUP_MISSING_OR_CHANGED: ' + entry['path'])
        sidecar = journal['sidecar']
        path = Path(sidecar['path'])
        if path != Path(self.build.ROOT) / 'dist-sidecar' / 'zara-backend.exe':
            raise ValueError('SIDECAR_PATH_MISMATCH')
        current = _file_digest(path)
        before = sidecar['before_sha256']
        candidate = journal['candidate_backend_sha256']
        if current != before and current != candidate:
            raise ValueError('SIDECAR_DRIFT_AFTER_PROMOTION')
        if before is not None and current != before:
            saved = sidecar.get('backup')
            if (not saved or Path(saved) != self.journal_path.parent / 'dist-sidecar' / 'zara-backend.exe'
                    or _file_digest(saved) != before):
                raise ValueError('SIDECAR_BACKUP_MISSING_OR_CHANGED')

    def _restore_source(self, journal):
        self._check_restore_source(journal)
        backup_dir = Path(journal['source_backup'])
        for entry in journal['source_entries']:
            relative = _safe_lab_overlay_path(entry['path'])
            target = _reject_symlinked_path(self.workspace, relative)
            if entry['before_sha256'] is None:
                if target.is_file():
                    target.unlink()
                continue
            if _file_digest(target) != entry['before_sha256']:
                shutil.copy2(backup_dir.joinpath(*relative.parts), target)
            if _file_digest(target) != entry['before_sha256']:
                raise ValueError('SOURCE_ROLLBACK_HASH_MISMATCH: ' + entry['path'])
        sidecar = Path(journal['sidecar']['path'])
        saved = Path(journal['sidecar']['backup']) if journal['sidecar'].get('backup') else None
        if _file_digest(sidecar) == journal['sidecar']['before_sha256']:
            pass
        elif saved and saved.is_file():
            shutil.copy2(saved, sidecar)
        elif journal['sidecar']['before_sha256'] is None and sidecar.is_file():
            sidecar.unlink()
        if _file_digest(sidecar) != journal['sidecar']['before_sha256']:
            raise ValueError('SIDECAR_ROLLBACK_HASH_MISMATCH')

    # -- activation ------------------------------------------------------
    def activate(self, package, validation):
        build = self.build
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        journal_dir = Path(build.ROOT) / 'artifacts/releases' / ('source-' + stamp)
        backup_dir = journal_dir / 'source-backup'
        sidecar = Path(build.ROOT) / 'dist-sidecar' / 'zara-backend.exe'
        sidecar_backup = journal_dir / 'dist-sidecar' / 'zara-backend.exe'
        self.journal_path = journal_dir / 'SOURCE_PROMOTION.json'
        source_package = Path(package).resolve(strict=True)
        if (source_package != Path(self.receipt['package']).resolve(strict=True)
                or Path(validation).resolve(strict=True)
                    != Path(self.receipt['canary_report']).resolve(strict=True)):
            raise ValueError('ACTIVATION_ARGUMENTS_DIFFER_FROM_RECEIPT')
        readiness = promotion_readiness(self.receipt, self.workspace, build)
        if not readiness.get('eligible'):
            raise ValueError('CANDIDATE_NO_LONGER_ELIGIBLE: ' + str(readiness.get('reason')))
        known = known_good(build)
        if not known.get('available'):
            raise ValueError('KNOWN_GOOD_ACTIVE_BUILD_UNAVAILABLE')
        before_source = build.source_identity()['sha256']
        pointer_paths = (Path(build.ROOT) / 'ZARA_ACTIVE_BUILD.json',
                         Path(build.ROOT) / 'ZARA_ACTIVE_BUILD.txt')
        previous_pointers = {path.name: path.read_text(encoding='utf-8') if path.is_file() else None
                             for path in pointer_paths}
        durable_package = Path(build.FRONTEND) / source_package.name
        if durable_package.exists():
            raise ValueError('PROMOTED_CANDIDATE_PATH_COLLISION')
        journal = {'state': 'PREPARED', 'activation_mode': 'ACTIVE_POINTER',
                   'candidate_package': str(durable_package),
                   'candidate_package_source': str(source_package),
                   'source_backup': str(backup_dir), 'before_source_sha256': before_source,
                   'candidate_source_sha256': self.receipt['source_sha256'],
                   'candidate_backend_sha256': _file_digest(self.receipt['backend_path']),
                   'workspace': str(self.workspace), 'candidate_workspace': str(self.staged),
                   'known_good': known, 'previous_pointers': previous_pointers,
                   'source_entries': [],
                   'sidecar': {'path': str(sidecar), 'before_sha256': _file_digest(sidecar),
                               'backup': None}}
        build.write_json(self.journal_path, journal)
        try:
            if journal['sidecar']['before_sha256'] is not None:
                sidecar_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sidecar, sidecar_backup)
                journal['sidecar']['backup'] = str(sidecar_backup)
            journal['source_entries'] = self._plan_source(backup_dir)
            journal.update(state='SOURCE_WRITING', source_entries_planned=True)
            build.write_json(self.journal_path, journal)
            self._apply_source(journal['source_entries'])
            candidate_backend = Path(self.receipt['backend_path'])
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_backend, sidecar)
            after_source = build.source_identity()['sha256']
            if after_source != self.receipt['source_sha256']:
                raise ValueError('PROMOTED_SOURCE_DOES_NOT_MATCH_CANDIDATE')
            if _file_digest(sidecar) != self.receipt['backend_sha256']:
                raise ValueError('PROMOTED_SIDECAR_DOES_NOT_MATCH_CANDIDATE')
            shutil.move(str(source_package), str(durable_package))
            info_path = durable_package / 'win-unpacked' / 'BUILD_INFO.json'
            info = json.loads(info_path.read_text(encoding='utf-8'))
            exe = durable_package / 'win-unpacked' / 'ZARA 3.0.exe'
            info['EXE_PATH'] = str(exe)
            info['STATUS'] = 'active-validated'
            info['SOURCE_PROMOTION_JOURNAL'] = str(self.journal_path)
            info['ROLLBACK_JOURNAL'] = str(self.journal_path)
            build.write_json(info_path, info)
            self.receipt['package'] = str(durable_package)
            self.receipt['exe_path'] = str(exe)
            self.receipt['asar_path'] = str(durable_package / 'win-unpacked' / 'resources' / 'app.asar')
            self.receipt['backend_path'] = str(durable_package / 'win-unpacked' / 'resources' / 'backend' / 'zara-backend.exe')
            journal.update(state='SOURCE_PROMOTED', after_source_sha256=after_source,
                           candidate_package=str(durable_package))
            build.write_json(self.journal_path, journal)
            new_pointer = dict(info)
            new_pointer['EXE_PATH'] = str(exe)
            journal.update(state='POINTER_WRITING', candidate_build_id=info['BUILD_ID'])
            build.write_json(self.journal_path, journal)
            build.write_json(pointer_paths[0], new_pointer)
            pointer_tmp = pointer_paths[1].with_name(pointer_paths[1].name + '.tmp')
            pointer_tmp.write_text(str(exe) + '\n', encoding='utf-8')
            os.replace(pointer_tmp, pointer_paths[1])
            journal.update(state='ACTIVATED', new_build_id=info['BUILD_ID'],
                           after_pointer_sha256=_file_digest(pointer_paths[0]))
            build.write_json(self.journal_path, journal)
        except Exception:
            try:
                self._check_restore_source(journal)
                self._check_restore_pointers(journal)
                self._restore_source(journal)
                self._restore_pointers(journal)
                after = promotion_evidence(journal, build)
                if after['coherent_state'] != 'KNOWN_GOOD':
                    raise ValueError('ACTIVATION_ROLLBACK_INCOMPLETE')
                journal.update(state='ACTIVATION_FAILED_RESTORED',
                               restored_source_sha256=build.source_identity()['sha256'],
                               candidate_quarantine=self._quarantine_candidate(durable_package, journal))
            except Exception as restore_exc:
                journal.update(state='RECONCILIATION_NEEDS_OWNER',
                               restore_error=type(restore_exc).__name__ + ': ' + str(restore_exc)[:400])
            build.write_json(self.journal_path, journal)
            raise
        self.journal = journal
        return dict(info, package=str(durable_package), SOURCE_PROMOTION_JOURNAL=str(self.journal_path))

    def _check_restore_pointers(self, journal):
        previous = journal.get('previous_pointers') or {}
        if set(previous) != {'ZARA_ACTIVE_BUILD.json', 'ZARA_ACTIVE_BUILD.txt'}:
            raise ValueError('POINTER_BACKUP_INCOMPLETE')
        candidate_exe = str(Path(journal['candidate_package']) / 'win-unpacked' / 'ZARA 3.0.exe')
        for name, before in previous.items():
            path = Path(self.build.ROOT) / name
            current = path.read_text(encoding='utf-8') if path.is_file() else None
            if current == before:
                continue
            if name.endswith('.txt') and current == candidate_exe + '\n':
                continue
            if name.endswith('.json') and current is not None:
                try:
                    pointer = json.loads(current)
                    baseline = known_good(self.build)
                    if (pointer.get('EXE_PATH') == candidate_exe
                            and baseline.get('available')
                            and baseline.get('path') == journal['candidate_package']
                            and baseline.get('build_id') == journal.get('new_build_id', journal.get('candidate_build_id'))):
                        continue
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            raise ValueError('ACTIVE_POINTER_DRIFT_AFTER_PROMOTION: ' + name)

    def _restore_pointers(self, journal):
        self._check_restore_pointers(journal)
        for name, value in (journal.get('previous_pointers') or {}).items():
            path = Path(self.build.ROOT) / name
            if value is None:
                if path.exists():
                    path.unlink()
                continue
            temporary = path.with_name(path.name + '.rollback.tmp')
            temporary.write_text(value, encoding='utf-8')
            os.replace(temporary, path)

    def _quarantine_candidate(self, package, journal):
        package = Path(package)
        if not package.is_dir():
            return None
        if (package.resolve().parent != Path(self.build.FRONTEND).resolve()
                or package.resolve() != Path(journal.get('candidate_package', '')).resolve()):
            raise ValueError('CANDIDATE_QUARANTINE_PATH_INVALID')
        quarantine = Path(self.build.ROOT) / '_quarentena' / 'lab-candidates'
        quarantine.mkdir(parents=True, exist_ok=True)
        destination = quarantine / (package.name + '-rolled-back')
        if destination.exists():
            destination = quarantine / (package.name + '-' + str(time.time_ns()))
        shutil.move(str(package), str(destination))
        manifest = {'status': 'AUTO_PROMOTION_ROLLED_BACK', 'reason': journal.get('state'),
                    'source_package': str(package), 'quarantine_path': str(destination),
                    'promotion_journal': str(self.journal_path), 'preserved_at': time.time()}
        (destination / 'QUARANTINE_MANIFEST.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return manifest

    #: States from which a rollback may still restore the pre-promotion
    #: known-good. ``ACTIVATED`` is the automatic post-activation window (see
    #: ``ReleaseQueue.promote``); ``HEALTH_PASSED``/``COMMITTED`` are added for
    #: ZARA-TELEGRAM-RESTAURAR-001: Alex asking, well after a promotion
    #: succeeded, to undo it because he does not like the result or it broke
    #: something the automatic health check did not catch. The journal already
    #: names its own known-good and its own package-level ``build_journal``, so
    #: rolling back from any of these three states restores exactly the same
    #: target this promotion would have restored to had health failed instead
    #: — no second reversal mechanism, only a later call to this same one.
    ROLLBACK_ELIGIBLE_STATES = frozenset({'ACTIVATED', 'HEALTH_PASSED', 'COMMITTED'})

    def rollback(self, build_journal=None):
        """Restore package, pointers, sidecar and source from one known-good."""
        build = self.build
        journal = self.journal or json.loads(self.journal_path.read_text(encoding='utf-8'))
        if journal.get('state') not in self.ROLLBACK_ELIGIBLE_STATES:
            raise ValueError('No promoted source release to roll back')
        journal.update(state='ROLLING_BACK')
        build.write_json(self.journal_path, journal)
        if journal.get('activation_mode') == 'ACTIVE_POINTER':
            self._check_restore_source(journal)
            self._check_restore_pointers(journal)
            self._restore_source(journal)
            self._restore_pointers(journal)
            after = build.source_identity()['sha256']
            if after != journal['before_source_sha256']:
                raise ValueError('SOURCE_ROLLBACK_INCOMPLETE')
            baseline = known_good(build)
            if not baseline.get('available') or baseline['build_id'] != journal['known_good']['build_id']:
                raise ValueError('PACKAGE_ROLLBACK_INCOMPLETE')
            if _file_digest(journal['sidecar']['path']) != journal['sidecar']['before_sha256']:
                raise ValueError('SIDECAR_ROLLBACK_INCOMPLETE')
            quarantined = self._quarantine_candidate(journal.get('candidate_package'), journal)
            journal.update(state='ROLLED_BACK', restored_source_sha256=after,
                           restored_build_id=baseline['build_id'],
                           candidate_quarantine=quarantined)
            build.write_json(self.journal_path, journal)
            self.journal = journal
            return {'state': 'ROLLED_BACK', 'restored_build_id': baseline['build_id'],
                    'candidate_quarantine': quarantined, 'SOURCE_ROLLED_BACK': True}
        restored = build.rollback_package(Path(build_journal or journal['build_journal']))
        self._restore_source(journal)
        after = build.source_identity()['sha256']
        if after != journal['before_source_sha256']:
            raise ValueError('SOURCE_ROLLBACK_INCOMPLETE')
        baseline = known_good(build)
        if not baseline.get('available') or baseline['build_id'] != journal['known_good']['build_id']:
            raise ValueError('PACKAGE_ROLLBACK_INCOMPLETE')
        journal.update(state='ROLLED_BACK', restored_source_sha256=after,
                       restored_build_id=baseline['build_id'])
        build.write_json(self.journal_path, journal)
        return dict(restored, SOURCE_ROLLED_BACK=True)

    def health(self, info):
        """Post-activation gate: the active package must verify against source."""
        if not self._verified_candidate(info['BUILD_ID']):
            return False
        if self.journal is not None:
            self.journal.update(state='HEALTH_PASSED')
            self.build.write_json(self.journal_path, self.journal)
        return True

    def commit(self, info=None):
        """Last deterministic step: declare the promotion durably finished."""
        journal = self.journal or json.loads(self.journal_path.read_text(encoding='utf-8'))
        if journal.get('state') != 'HEALTH_PASSED':
            raise ValueError('COMMIT_REQUIRES_PASSED_HEALTH_CHECK')
        journal.update(state='COMMITTED', committed_at=time.time())
        self.build.write_json(self.journal_path, journal)
        self.journal = journal
        return journal

    def _verified_candidate(self, build_id):
        """Package + pointers + source + sidecar must all verify as the candidate."""
        journal = self.journal or {}
        if journal.get('activation_mode') == 'ACTIVE_POINTER':
            try:
                pointer = json.loads((Path(self.build.ROOT) / 'ZARA_ACTIVE_BUILD.json').read_text(encoding='utf-8'))
                package = Path(pointer['EXE_PATH']).resolve(strict=True).parent.parent
                info = json.loads((package / 'win-unpacked' / 'BUILD_INFO.json').read_text(encoding='utf-8'))
                artifacts = {key: _file_digest(path) for key, path in self.build.packaged_paths(package).items()}
                return (pointer.get('BUILD_ID') == build_id == info.get('BUILD_ID')
                        and pointer.get('EXE_PATH') == info.get('EXE_PATH')
                        and all(_same_digest(artifacts.get(key), info.get(key))
                                and _same_digest(pointer.get(key), info.get(key))
                                for key in artifacts)
                        and Path(package).resolve() == Path(journal.get('candidate_package', '')).resolve()
                        and info.get('SOURCE_SHA256') == journal.get('candidate_source_sha256')
                        and self.build.source_identity()['sha256'] == journal.get('candidate_source_sha256')
                        and _file_digest(journal.get('sidecar', {}).get('path', ''))
                            == journal.get('candidate_backend_sha256'))
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                return False
        try:
            verified = self.build.verify_package(Path(self.build.CURRENT))
        except (OSError, ValueError, KeyError):
            return False
        return verified.get('BUILD_ID') == build_id

    # -- crash recovery ---------------------------------------------------
    @classmethod
    def from_journal(cls, journal_path, *, build=None):
        """Rebuild a promotion object from its journal alone, after a crash."""
        build = _build_module(build)
        journal_path = Path(journal_path)
        journal = json.loads(journal_path.read_text(encoding='utf-8'))
        build = _build_module(build, journal.get('workspace'))
        promotion = cls(journal.get('workspace') or build.ROOT,
                        {'workspace': journal.get('candidate_workspace') or build.ROOT,
                         'overlay': [], 'source_sha256': journal.get('candidate_source_sha256')},
                        build=build)
        promotion.journal_path = journal_path
        promotion.journal = journal
        return promotion

    def _record(self, action, state, evidence, reason, **extra):
        journal = self.journal
        record = dict({'action': action, 'reason': reason, 'from_state': journal.get('state'),
                       'to_state': state, 'evidence': evidence, 'at': time.time()}, **extra)
        journal['state'] = state
        journal.setdefault('reconciliations', []).append(record)
        self.build.write_json(self.journal_path, journal)
        return dict(record, journal=str(self.journal_path))

    def _discard_staging(self, journal):
        """A staging copy is disposable; an interrupted copytree is never reused."""
        staged = journal.get('staged_package')
        if staged and Path(staged).is_dir() and Path(staged) != Path(self.build.CURRENT):
            shutil.rmtree(staged, ignore_errors=True)

    def _restore_package(self, journal):
        """Bring the active package back to the recorded known-good, by evidence."""
        build = self.build
        found = _build_journal_for(build, journal.get('staged_package'))
        if found is None:
            return 'PACKAGE_NEVER_ACTIVATED'
        path, document = found
        state = document.get('state')
        if state == 'ACTIVATED':
            build.rollback_package(path)
            return 'PACKAGE_ROLLED_BACK'
        if state in ('ROLLED_BACK', 'ACTIVATION_FAILED_RESTORED'):
            return 'PACKAGE_ALREADY_RESTORED'
        return self._restore_interrupted_package(path, document)

    def _restore_interrupted_package(self, path, document):
        """activate_package died between its two renames; put the baseline back."""
        build = self.build
        current, backup = Path(build.CURRENT), Path(document['backup'])
        previous = document.get('previous_info') or {}
        if current.exists():
            try:
                info = json.loads((current / 'win-unpacked' / 'BUILD_INFO.json').read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                info = {}
            if info.get('BUILD_ID') != previous.get('BUILD_ID'):
                stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                current.rename(Path(build.FRONTEND) / ('.current-build-staging-rollback-' + stamp))
            else:
                backup = None
        if backup is not None:
            if not backup.is_dir():
                raise ValueError('PACKAGE_BASELINE_MISSING')
            for key, artifact in build.packaged_paths(backup).items():
                if build.digest(artifact) != previous.get(key):
                    raise ValueError('PACKAGE_BASELINE_FAILED_INTEGRITY')
            backup.rename(current)
        for name, value in (document.get('previous_pointers') or {}).items():
            pointer = Path(build.ROOT) / name
            if value is not None:
                pointer.write_text(value, encoding='utf-8')
            elif pointer.exists():
                pointer.unlink()
        document.update(state='ROLLED_BACK', reconciled=True)
        build.write_json(path, document)
        return 'PACKAGE_RESTORED_FROM_INTERRUPTED_ACTIVATION'

    def reconcile(self):
        """Drive an interrupted promotion to exactly one coherent state.

        The promotion is finished only when the health check already passed and
        the whole runtime still verifies as the candidate; every other outcome —
        including any state whose evidence is mixed or uncertain — rolls back to
        the recorded known-good. No uncertain effect is ever replayed blindly.
        """
        journal = self.journal
        state = journal.get('state')
        if state in TERMINAL_PROMOTION_STATES:
            return {'action': 'NONE', 'reason': 'ALREADY_TERMINAL', 'from_state': state,
                    'to_state': state, 'journal': str(self.journal_path), 'evidence': None}
        evidence = promotion_evidence(journal, self.build)
        if journal.get('activation_mode') == 'ACTIVE_POINTER':
            if (state == 'HEALTH_PASSED' and evidence['coherent_state'] == 'CANDIDATE'
                    and self._verified_candidate(journal.get('new_build_id'))):
                return self._record('COMPLETED_PROMOTION', 'RECONCILED_COMMITTED', evidence,
                                    'HEALTH_ALREADY_PASSED_ONLY_THE_COMMIT_WAS_MISSING')
            try:
                self._check_restore_source(journal)
                self._check_restore_pointers(journal)
                self._restore_source(journal)
                self._restore_pointers(journal)
                after = promotion_evidence(journal, self.build)
                if after['coherent_state'] != 'KNOWN_GOOD':
                    raise ValueError('ROLLBACK_DID_NOT_REACH_KNOWN_GOOD')
                quarantined = self._quarantine_candidate(journal.get('candidate_package'), journal)
            except (OSError, ValueError, KeyError) as exc:
                after = promotion_evidence(journal, self.build)
                return self._record('BLOCKED', 'RECONCILIATION_NEEDS_OWNER', evidence,
                                    'ROLLBACK_FAILED: ' + type(exc).__name__ + ': ' + str(exc)[:400],
                                    evidence_after=after)
            return self._record('ROLLED_BACK', 'RECONCILED_KNOWN_GOOD', evidence,
                                'INTERRUPTED_PROMOTION_WAS_NOT_PROVEN_HEALTHY',
                                candidate_quarantine=quarantined, evidence_after=after)
        if state == 'HEALTH_PASSED' and evidence['coherent_state'] == 'CANDIDATE' \
                and self._verified_candidate(journal.get('new_build_id')):
            self._discard_staging(journal)
            return self._record('COMPLETED_PROMOTION', 'RECONCILED_COMMITTED', evidence,
                                'HEALTH_ALREADY_PASSED_ONLY_THE_COMMIT_WAS_MISSING')
        if evidence['coherent_state'] == 'KNOWN_GOOD':
            self._discard_staging(journal)
            return self._record('NO_CHANGE_TO_UNDO', 'RECONCILED_KNOWN_GOOD', evidence,
                                'CRASH_LEFT_THE_KNOWN_GOOD_INTACT')
        try:
            package_result = self._restore_package(journal)
            self._restore_source(journal)
            self._discard_staging(journal)
        except (OSError, ValueError, KeyError) as exc:
            after = promotion_evidence(journal, self.build)
            return self._record('BLOCKED', 'RECONCILIATION_NEEDS_OWNER', evidence,
                                'ROLLBACK_FAILED: ' + type(exc).__name__ + ': ' + str(exc)[:400],
                                evidence_after=after)
        after = promotion_evidence(journal, self.build)
        if after['coherent_state'] != 'KNOWN_GOOD':
            return self._record('BLOCKED', 'RECONCILIATION_NEEDS_OWNER', evidence,
                                'ROLLBACK_DID_NOT_REACH_A_SINGLE_KNOWN_GOOD_STATE',
                                package_result=package_result, evidence_after=after)
        return self._record('ROLLED_BACK', 'RECONCILED_KNOWN_GOOD', evidence,
                            'INTERRUPTED_PROMOTION_WAS_NOT_PROVEN_HEALTHY',
                            package_result=package_result, evidence_after=after)


def _promotion_journals(build):
    folder = Path(build.ROOT) / 'artifacts' / 'releases'
    return sorted(folder.glob('source-*/SOURCE_PROMOTION.json')) if folder.is_dir() else []


def pending_promotions(build=None):
    """Read-only: promotion journals that were never resolved into one state.

    A journal stopped at ``RECONCILIATION_NEEDS_OWNER`` stays here forever: the
    machine already tried and could not prove a single coherent state, so the
    runtime is still owned by that unresolved promotion. It leaves this list
    only when a human resolves the journal on disk — the same contract
    ``LabV1Service._unresolved_promotions`` uses to keep refusing mission entry.
    """
    build = _build_module(build)
    pending = []
    for path in _promotion_journals(build):
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pending.append({'journal': str(path), 'state': 'UNREADABLE', 'needs_owner': True})
            continue
        state = document.get('state')
        if state not in RESOLVED_PROMOTION_STATES:
            pending.append({'journal': str(path), 'state': state,
                            'needs_owner': state in OWNER_RESOLUTION_REQUIRED_STATES})
    return pending


def reconcile_promotions(build=None):
    """Restart hook: reconcile every incomplete source promotion journal."""
    build = _build_module(build)
    with _promotion_lock(build):
        return [SourcePromotion.from_journal(path, build=build).reconcile()
                for path in _promotion_journals(build)]


def most_recent_promotion(build=None):
    """Read-only: the journal of the last source promotion ever attempted.

    ZARA-TELEGRAM-RESTAURAR-001: a deliberate "restaurar"/"voltar" request from
    the owner, asked at any later time, has exactly one honest target — the
    most recent promotion — never a menu of historical checkpoints. Filenames
    are timestamp-ordered (``source-YYYYMMDD-HHMMSS-ffffff``), so the same
    lexicographic sort ``_promotion_journals`` already uses is chronological.
    """
    build = _build_module(build)
    journals = _promotion_journals(build)
    if not journals:
        return None
    path = journals[-1]
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'journal': str(path), 'state': 'UNREADABLE'}
    return {'journal': str(path), 'state': document.get('state')}
