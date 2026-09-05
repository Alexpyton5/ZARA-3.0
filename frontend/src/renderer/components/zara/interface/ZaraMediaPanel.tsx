import React from 'react';

export const ZaraMediaPanel: React.FC = () => {
  return (
    <div className="zara-panel-card" style={{ padding: '13px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ fontSize: '14.5px', fontWeight: 600, color: 'var(--txt-1)' }}>Mídia</div>
      <div style={{ color: 'var(--txt-3)', fontSize: '12px' }}>Painel de mídia será implementado aqui.</div>
    </div>
  );
};