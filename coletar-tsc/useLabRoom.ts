import { useCallback, useEffect, useRef, useState } from 'react';
import { asList, failureText, requireResult, type Snapshot } from './labTypes';
import { recoverDurableLabMutations } from '../../lib/labDurableOperation';

function savedRoom() {
  try { const value = JSON.parse(localStorage.getItem('zara.lab.selection.v1') || '{}');
    return { sessionId: typeof value.sessionId === 'string' ? value.sessionId : '', teamId: typeof value.teamId === 'string' ? value.teamId : '' };
  } catch { return { sessionId: '', teamId: '' }; }
}

/** Polls persisted snapshots only. Changing rooms invalidates older in-flight reads. */
export function useLabRoom() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [sessionId, setSessionId] = useState(() => savedRoom().sessionId);
  const [teamId, setTeamId] = useState(() => savedRoom().teamId);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastSynced, setLastSynced] = useState(0);
  const selected = useRef({ sessionId, teamId });
  const generation = useRef(0);
  const mounted = useRef(true);
  const pendingRead = useRef<Promise<void> | null>(null);
  const refreshQueued = useRef(false);
  const seenOperationEvents = useRef<Set<string>>(new Set());
  const refresh = useCallback(async () => {
    const revision = generation.current;
    if (pendingRead.current) {
      refreshQueued.current = true;
      return pendingRead.current;
    }
    const request = (async () => {
      try {
        const next = requireResult(await window.zaraIPC?.labV1?.snapshot?.(selected.current.sessionId || undefined, selected.current.teamId || undefined)) as Snapshot;
        if (!mounted.current || revision !== generation.current) return;
        if (!selected.current.sessionId) {
          const latest = asList(next.sessions).filter(session => !selected.current.teamId || session.team_id === selected.current.teamId).sort((a, b) => b.updated_at - a.updated_at)[0];
          if (latest) {
            selected.current = { sessionId: latest.id, teamId: latest.team_id };
            setSessionId(latest.id); setTeamId(latest.team_id);
            const expanded = requireResult(await window.zaraIPC?.labV1?.snapshot?.(latest.id, latest.team_id)) as Snapshot;
            if (!mounted.current || revision !== generation.current) return;
            setSnapshot(expanded);
          } else { setSnapshot(next); }
        } else setSnapshot(next);
        setError(''); setLastSynced(Date.now());
      } catch (cause) {
        const failure = failureText(cause);
        // The saved room is only a renderer convenience. A deleted/replaced
        // backend database must not leave the whole Lab permanently pinned to
        // a session that no longer exists.
        if (/sess[aã]o n[aã]o encontrada/i.test(failure) && selected.current.sessionId) {
          selected.current = { sessionId: '', teamId: '' };
          try { localStorage.removeItem('zara.lab.selection.v1'); } catch { /* backend remains authoritative */ }
          setSessionId(''); setTeamId('');
          try {
            const recovered = requireResult(await window.zaraIPC?.labV1?.snapshot?.()) as Snapshot;
            if (!mounted.current || revision !== generation.current) return;
            const latest = asList(recovered.sessions).sort((a, b) => b.updated_at - a.updated_at)[0];
            if (latest) {
              selected.current = { sessionId: latest.id, teamId: latest.team_id };
              setSessionId(latest.id); setTeamId(latest.team_id);
              try { localStorage.setItem('zara.lab.selection.v1', JSON.stringify(selected.current)); } catch { /* optional cache */ }
              setSnapshot(requireResult(await window.zaraIPC?.labV1?.snapshot?.(latest.id, latest.team_id)) as Snapshot);
            } else setSnapshot(recovered);
            setError(''); setLastSynced(Date.now());
            return;
          } catch (recoveryCause) {
            if (mounted.current && revision === generation.current) setError(failureText(recoveryCause));
            return;
          }
        }
        if (mounted.current && revision === generation.current) setError(failure);
      }
      finally { if (mounted.current && revision === generation.current) setLoading(false); }
    })();
    pendingRead.current = request;
    void request.finally(() => {
      if (pendingRead.current === request) pendingRead.current = null;
      if (!mounted.current) { refreshQueued.current = false; return; }
      if (refreshQueued.current) {
        refreshQueued.current = false;
        void refresh();
      }
    });
    return request;
  }, []);
  const select = useCallback((nextSessionId = '', nextTeamId = '') => {
    generation.current += 1;
    selected.current = { sessionId: nextSessionId, teamId: nextTeamId };
    try { localStorage.setItem('zara.lab.selection.v1', JSON.stringify(selected.current)); } catch { /* backend persistence remains authoritative */ }
    setSessionId(nextSessionId); setTeamId(nextTeamId); setError(''); setLoading(true);
    setSnapshot(current => current ? { ...current, session: null } : null);
    void refresh();
  }, [refresh]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    void recoverDurableLabMutations(window.zaraIPC?.labV1 || {}).catch(cause => {
      if (mounted.current) setError(failureText(cause));
    }).finally(refresh);
    const interval = setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
    const visible = () => { if (!document.hidden) void refresh(); };
    const unsubscribe = window.zaraIPC?.on?.labOperationResult?.((event) => {
      const eventKey = event.event_id || event.operation_id;
      if (eventKey) {
        if (seenOperationEvents.current.has(eventKey)) return;
        seenOperationEvents.current.add(eventKey);
        if (seenOperationEvents.current.size > 256) {
          const first = seenOperationEvents.current.values().next().value;
          if (first) seenOperationEvents.current.delete(first);
        }
      }
      if (!event.session_id || !selected.current.sessionId || event.session_id === selected.current.sessionId) void refresh();
    });
    document.addEventListener('visibilitychange', visible);
    return () => { mounted.current = false; generation.current += 1; refreshQueued.current = false; clearInterval(interval); unsubscribe?.(); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);
  return { snapshot, sessionId, teamId, loading, error, lastSynced, select, refresh };
}
