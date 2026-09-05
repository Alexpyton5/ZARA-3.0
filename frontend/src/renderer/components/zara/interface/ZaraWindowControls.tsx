import React from 'react';

export const ZaraWindowControls: React.FC = () => {
  return (
    <div className="zara-window-controls">
      <button className="zara-window-btn zara-window-btn-minimize" aria-label="Minimizar">
        <svg width="10" height="10" viewBox="0 0 12 12"><path d="M1.5 6h9" stroke="white" strokeWidth="1.5" strokeLinecap="round"/></svg>
      </button>
      <button className="zara-window-btn zara-window-btn-maximize" aria-label="Maximizar">
        <svg width="10" height="10" viewBox="0 0 12 12"><rect x="1.5" y="1.5" width="9" height="9" rx="1" stroke="white" strokeWidth="1.5"/></svg>
      </button>
      <button className="zara-window-btn zara-window-btn-close" aria-label="Fechar">
        <svg width="10" height="10" viewBox="0 0 12 12"><path d="M2 2 10 10M10 2 2 10" stroke="white" strokeWidth="1.5" strokeLinecap="round"/></svg>
      </button>
    </div>
  );
};