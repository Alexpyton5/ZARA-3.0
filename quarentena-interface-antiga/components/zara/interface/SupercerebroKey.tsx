import React, { useCallback, useEffect, useState } from 'react';

// Chave manual do Super Cerebro (decisao do Alex, 27/09):
// VERDE (ON) = ele monitorando; VERMELHO (OFF) = sozinho.
// A chave e local -- sem Hermes, sem dependencia externa.
// O estado real vem do backend via window.zaraIPC (preload -> main -> Python).
export const SupercerebroKey: React.FC = () => {
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    const sc = window.zaraIPC?.supercerebro;
    if (sc?.status) {
      sc.status().then((s: any) => {
        if (mounted && s) setActive(!!s.active);
      }).catch(() => { /* mantem OFF ate o backend responder */ });
    }
    let unsub: (() => void) | undefined;
    const sub = window.zaraIPC?.on?.supercerebroChange;
    if (sub) {
      unsub = sub((v: boolean) => {
        if (mounted) setActive(!!v);
      });
    }
    return () => {
      mounted = false;
      if (unsub) unsub();
    };
  }, []);

  const onClick = useCallback(async () => {
    const sc = window.zaraIPC?.supercerebro;
    if (!sc?.toggle || busy) return;
    setBusy(true);
    try {
      const r = await sc.toggle(!active);
      if (r && typeof r.active === 'boolean') setActive(r.active);
    } catch {
      /* o estado real chega pelo evento supercerebro-change */
    } finally {
      setBusy(false);
    }
  }, [active, busy]);

  return (
    <button
      onClick={onClick}
      disabled={busy}
      title={active
        ? 'Super Cerebro ligado -- o Alex esta monitorando. Clique para desligar.'
        : 'Super Cerebro desligado. Clique para ligar.'}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '7px 14px',
        borderRadius: '999px',
        cursor: busy ? 'wait' : 'pointer',
        border: '1px solid ' + (active ? '#22c55e' : '#ef4444'),
        background: active ? 'rgba(34,197,94,0.14)' : 'rgba(239,68,68,0.10)',
        color: 'var(--txt-1)',
        fontSize: '12.5px',
        fontWeight: 600,
      }}
    >
      <span
        style={{
          width: '9px',
          height: '9px',
          borderRadius: '50%',
          background: active ? '#22c55e' : '#ef4444',
          boxShadow: active ? '0 0 8px #22c55e' : 'none',
        }}
      />
      {active ? 'Super Cerebro ON' : 'Super Cerebro OFF'}
    </button>
  );
};
