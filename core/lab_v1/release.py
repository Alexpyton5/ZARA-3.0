"""Durable gates for candidate package, canary, activation, monitor and rollback."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import time

from core.lab_v1.evolution import WORKFLOW
from core.lab_v1.evolution_repairs import REPAIR_ID, digest
from core.lab_v1.workforce_policy import WorkforcePolicy

SOURCE_WORKFLOW = 'source_mission'


class ReleaseQueue:
    TERMINAL = frozenset({'ACTIVE', 'ROLLED_BACK', 'BLOCKED'})

    def __init__(self, store, *, policy=None):
        self.store = store
        self.policy = policy or WorkforcePolicy(WorkforcePolicy.default_document())
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
        readiness = promotion_readiness(receipt, workspace)
        if not readiness['eligible']:
            raise ValueError('Release requires a promotable candidate: ' + readiness['reason'])
        return self.update(sid, state='PACKAGE_PENDING', workflow=SOURCE_WORKFLOW,
            candidate=str(Path(receipt['package']).resolve()),
            candidate_source_sha256=receipt['source_sha256'],
            readiness=readiness, current_preserved=True)

    def package_ready(self, sid, package, package_info):
        doc = self.snapshot(sid)
        if not doc or doc.get('state') != 'PACKAGE_PENDING':
            raise ValueError('Package gate is not ready')
        package = Path(package).resolve(strict=True)
        required = ('BUILD_ID', 'SOURCE_SHA256', 'ASAR_SHA256', 'BACKEND_SHA256')
        if any(not package_info.get(key) for key in required):
            raise ValueError('Package identity is incomplete')
        return self.update(sid, state='CANARY_PENDING', package=str(package),
            build_id=package_info['BUILD_ID'], package_source_sha256=package_info['SOURCE_SHA256'],
            asar_sha256=package_info['ASAR_SHA256'], backend_sha256=package_info['BACKEND_SHA256'])

    def accept_canary(self, sid, validation):
        doc = self.snapshot(sid)
        if not doc or doc.get('state') != 'CANARY_PENDING':
            raise ValueError('Canary gate is not ready')
        validation = Path(validation).resolve(strict=True)
        report = json.loads(validation.read_text(encoding='utf-8'))
        if (report.get('status') != 'passed' or report.get('asar_sha256') != doc['asar_sha256']
                or report.get('backend_sha256') != doc['backend_sha256']):
            raise ValueError('Canary does not identify the queued package')
        return self.update(sid, state='READY_TO_ACTIVATE', validation=str(validation),
                           canary_accepted_at=time.time())

    def promote(self, sid, *, activate, monitor, rollback, commit=None):
        """Activate once; a failed post-activation monitor rolls back immediately."""
        doc = self.snapshot(sid)
        if not doc or doc.get('state') != 'READY_TO_ACTIVATE':
            raise ValueError('Activation gate is not ready')
        self.update(sid, state='ACTIVATING')
        try:
            info = activate(Path(doc['package']), Path(doc['validation']))
        except Exception as exc:
            self.update(sid, state='BLOCKED', error=type(exc).__name__ + ': ACTIVATION_RESTORED')
            raise
        journal = Path(info['ROLLBACK_JOURNAL'])
        self.update(sid, state='MONITORING', rollback_journal=str(journal),
                    active_build_id=info['BUILD_ID'])
        try:
            healthy = monitor(info)
        except Exception:
            healthy = False
        if healthy is not True:
            rollback(journal)
            return self.update(sid, state='ROLLED_BACK', error='POST_ACTIVATION_MONITOR_FAILED',
                               current_preserved=True)
        with self.store._connect() as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lab_evolution'").fetchone()
            row = conn.execute('SELECT document FROM lab_evolution WHERE session_id=?', (sid,)).fetchone() if exists else None
            if row:
                evolution = json.loads(row[0]); evolution.update(build_state='ACTIVE',
                    build_id=info['BUILD_ID'], learned_outcome='PROMOTION_MONITORED_PASS')
                conn.execute('UPDATE lab_evolution SET document=? WHERE session_id=?',
                             (json.dumps(evolution), sid))
        doc = self.update(sid, state='ACTIVE', build_id=info['BUILD_ID'], monitored=True)
        if commit is not None:
            commit(info)
        return doc


def _build_module(build=None):
    if build is not None:
        return build
    from tools import build_current
    return build_current


def _file_digest(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def known_good(build=None):
    """Identity of the package that a rollback would have to restore exactly."""
    build = _build_module(build)
    current = Path(build.CURRENT)
    info_path = current / 'win-unpacked' / 'BUILD_INFO.json'
    try:
        info = json.loads(info_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'available': False, 'reason': 'CURRENT_BUILD_INFO_UNREADABLE'}
    artifacts = {key: _file_digest(path) for key, path in build.packaged_paths(current).items()}
    if any(artifacts[key] != info.get(key) for key in artifacts):
        return {'available': False, 'reason': 'CURRENT_ARTIFACTS_DO_NOT_MATCH_BUILD_INFO',
                'build_id': info.get('BUILD_ID'), 'artifacts': artifacts}
    return {'available': True, 'build_id': info.get('BUILD_ID'), 'path': str(current),
            'artifacts': artifacts,
            'pointers': {name: _file_digest(Path(build.ROOT) / name)
                         for name in ('ZARA_ACTIVE_BUILD.json', 'ZARA_ACTIVE_BUILD.txt')}}


def promotion_readiness(receipt, workspace, build=None):
    """Decide, without mutating anything, whether this candidate may be promoted."""
    build = _build_module(build)
    workspace = Path(workspace).resolve()

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
    report_path = Path(receipt.get('canary_report', ''))
    try:
        if json.loads(report_path.read_text(encoding='utf-8')) != canary:
            return refuse('CANARY_REPORT_DOES_NOT_MATCH_RECEIPT')
    except (OSError, json.JSONDecodeError):
        return refuse('CANARY_REPORT_MISSING')
    identity = {}
    for key in ('exe', 'asar', 'backend'):
        actual = _file_digest(receipt.get(key + '_path', ''))
        if actual is None or actual != receipt.get(key + '_sha256'):
            return refuse('CANDIDATE_ARTIFACT_DRIFT', artifact=key)
        identity[key + '_sha256'] = actual
    overlay = receipt.get('overlay')
    staged = Path(receipt.get('workspace', ''))
    if not isinstance(overlay, list) or not overlay or not staged.is_dir():
        return refuse('CANDIDATE_OVERLAY_UNAVAILABLE')
    for item in overlay:
        if _file_digest(staged.joinpath(*Path(item['path']).parts)) != item.get('sha256'):
            return refuse('CANDIDATE_OVERLAY_DRIFT', path=item.get('path'))
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
        self.build = _build_module(build)
        self.workspace = Path(workspace).resolve()
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
            relative = Path(item['path'])
            target = self.workspace.joinpath(*relative.parts)
            origin = self.staged.joinpath(*relative.parts)
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
            target = self.workspace.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.staged.joinpath(*relative.parts), target)
            if _file_digest(target) != entry['after_sha256']:
                raise ValueError('PROMOTED_SOURCE_HASH_MISMATCH: ' + entry['path'])

    def _restore_source(self, journal):
        backup_dir = Path(journal['source_backup'])
        for entry in journal['source_entries']:
            relative = Path(entry['path'])
            target = self.workspace.joinpath(*relative.parts)
            if entry['before_sha256'] is None:
                if target.is_file():
                    target.unlink()
                continue
            shutil.copy2(backup_dir.joinpath(*relative.parts), target)
            if _file_digest(target) != entry['before_sha256']:
                raise ValueError('SOURCE_ROLLBACK_HASH_MISMATCH: ' + entry['path'])
        sidecar = Path(journal['sidecar']['path'])
        saved = Path(journal['sidecar']['backup']) if journal['sidecar'].get('backup') else None
        if saved and saved.is_file():
            shutil.copy2(saved, sidecar)
        elif journal['sidecar']['before_sha256'] is None and sidecar.is_file():
            sidecar.unlink()

    # -- activation ------------------------------------------------------
    def activate(self, package, validation):
        build = self.build
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        journal_dir = Path(build.ROOT) / 'artifacts/releases' / ('source-' + stamp)
        backup_dir = journal_dir / 'source-backup'
        sidecar = Path(build.ROOT) / 'dist-sidecar' / 'zara-backend.exe'
        sidecar_backup = journal_dir / 'dist-sidecar' / 'zara-backend.exe'
        self.journal_path = journal_dir / 'SOURCE_PROMOTION.json'
        before_source = build.source_identity()['sha256']
        journal = {'state': 'PREPARED', 'candidate_package': str(Path(package).resolve()),
                   'source_backup': str(backup_dir), 'before_source_sha256': before_source,
                   'candidate_source_sha256': self.receipt['source_sha256'],
                   'candidate_backend_sha256': _file_digest(self.receipt['backend_path']),
                   'workspace': str(self.workspace), 'candidate_workspace': str(self.staged),
                   'known_good': known_good(build), 'source_entries': [],
                   'sidecar': {'path': str(sidecar), 'before_sha256': _file_digest(sidecar),
                               'backup': None}}
        build.write_json(self.journal_path, journal)
        staged_package = None
        try:
            if journal['sidecar']['before_sha256'] is not None:
                sidecar_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sidecar, sidecar_backup)
                journal['sidecar']['backup'] = str(sidecar_backup)
            journal['source_entries'] = self._plan_source(backup_dir)
            journal.update(state='SOURCE_WRITING')
            build.write_json(self.journal_path, journal)
            self._apply_source(journal['source_entries'])
            candidate_backend = Path(self.receipt['backend_path'])
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_backend, sidecar)
            after_source = build.source_identity()['sha256']
            if after_source != self.receipt['source_sha256']:
                raise ValueError('PROMOTED_SOURCE_DOES_NOT_MATCH_CANDIDATE')
            journal.update(state='SOURCE_PROMOTED', after_source_sha256=after_source)
            build.write_json(self.journal_path, journal)
            staged_package = Path(build.FRONTEND) / ('.current-build-staging-promote-' + stamp)
            journal.update(state='PACKAGE_ACTIVATING', staged_package=str(staged_package))
            build.write_json(self.journal_path, journal)
            shutil.copytree(Path(package), staged_package)
            info = build.activate_package(staged_package, Path(validation))
        except Exception:
            if staged_package is not None and staged_package.is_dir():
                shutil.rmtree(staged_package, ignore_errors=True)
            self._restore_source(journal)
            journal.update(state='ACTIVATION_FAILED_RESTORED',
                           restored_source_sha256=build.source_identity()['sha256'])
            build.write_json(self.journal_path, journal)
            raise
        journal.update(state='ACTIVATED', build_journal=info['ROLLBACK_JOURNAL'],
                       new_build_id=info['BUILD_ID'])
        build.write_json(self.journal_path, journal)
        self.journal = journal
        return dict(info, SOURCE_PROMOTION_JOURNAL=str(self.journal_path))

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
