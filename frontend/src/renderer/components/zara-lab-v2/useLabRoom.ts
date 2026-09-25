import { useCallback, useEffect, useRef, useState } from 'react';
import { asList, failureText, requireResult, type Snapshot } from './labTypes';

function savedRoom() {
  // V1 could persist the legacy conversation team and reopen the Lab with no
  // Core participants or autonomous missions visible. Start V2 on Core once;
  // subsequent selections are still remembered normally.
  try { const value = JSON.parse(localStorage.getItem('zara.lab.selection.v2') || '{}');
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
  const pendingRead = useRef<number | null>(null);
  const refresh = useCallback(async () => {
    const revision = generation.current;
    if (pendingRead.current === revision) return;
    pendingRead.current = revision;
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
    } catch (cause) { if (mounted.current && revision === generation.current) setError(failureText(cause)); }
    finally { if (pendingRead.current === revision) pendingRead.current = null; if (mounted.current && revision === generation.current) setLoading(false); }
  }, []);
  const select = useCallback((nextSessionId = '', nextTeamId = '') => {
    generation.current += 1;
    selected.current = { sessionId: nextSessionId, teamId: nextTeamId };
    try { localStorage.setItem('zara.lab.selection.v2', JSON.stringify(selected.current)); } catch { /* backend persistence remains authoritative */ }
    setSessionId(nextSessionId); setTeamId(nextTeamId); setError(''); setLoading(true);
    setSnapshot(current => current ? { ...current, session: null } : null);
    void refresh();
  }, [refresh]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const interval = setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { mounted.current = false; generation.current += 1; clearInterval(interval); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);
  return { snapshot, sessionId, teamId, loading, error, lastSynced, select, refresh };
}
