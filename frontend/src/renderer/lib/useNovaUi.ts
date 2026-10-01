import { useCallback, useEffect, useRef, useState } from 'react';
import { parseNovaUiState, requireActionResult, type NovaUiState } from './novaUiState';
import { avatarOriginal } from '../components/zara-nova/avatares';
import type { AvatarInfo } from '../components/zara-nova/types';
import type { PilotProvider } from './pilotConversation';

export function useNovaUi(provider: PilotProvider = 'muse') {
  const [state, setState] = useState<NovaUiState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  const fetching = useRef(false);
  const mutating = useRef(false);
  const refresh = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      if (!window.zaraIPC?.novaUI) throw new Error('A conexão com a equipe ainda não está disponível.');
      const snapshot = parseNovaUiState(await window.zaraIPC.novaUI.state());
      const face = (avatar: AvatarInfo): AvatarInfo => ({ ...avatar, imagemUrl: avatar.imagemUrl || (provider === 'muse' ? avatarOriginal(avatar.id) : undefined) });
      snapshot.work = snapshot.work.map(item => ({ ...item, responsavel: face(item.responsavel) }));
      snapshot.activity = snapshot.activity.map(item => ({ ...item, responsavel: face(item.responsavel) }));
      snapshot.projects = snapshot.projects.map(project => ({ ...project, membros: project.membros.map(member => ({ ...member, avatar: face(member.avatar) })) }));
      if (alive.current) { setState(snapshot); setError(''); }
    } catch (cause) {
      if (alive.current) setError(cause instanceof Error ? cause.message : 'Não consegui atualizar a equipe.');
    } finally { fetching.current = false; }
  }, [provider]);
  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { alive.current = false; window.clearInterval(timer); };
  }, [refresh]);

  const pause = useCallback(async () => {
    if (mutating.current) return;
    if (!state || state.paused === null) throw new Error('Espere o motor confirmar o estado da equipe.');
    mutating.current = true; setBusy(true);
    try {
      const api = window.zaraIPC?.novaUI;
      if (!api) throw new Error('A conexão com o motor está indisponível.');
      const result = await (state.paused ? api.resume() : api.pause());
      await refresh();
      requireActionResult(result, 'O motor não confirmou a mudança.');
    } finally { mutating.current = false; setBusy(false); }
  }, [state, refresh]);
  const decide = useCallback(async (id: string, option: string) => {
    const api = window.zaraIPC?.novaUI;
    if (!api) throw new Error('A conexão com o motor está indisponível.');
    requireActionResult(await api.decide(id, option), 'Não consegui registrar essa decisão.');
    await refresh();
  }, [refresh]);
  return { state, error, busy, refresh, pause, decide };
}
