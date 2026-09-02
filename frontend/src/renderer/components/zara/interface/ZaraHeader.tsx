import React from 'react';

export const ZaraHeader: React.FC = () => {
  return (
    <header className="zara-header">
      <div className="zara-header-greeting">
        <div className="zara-header-greeting-title">Boa noite, Alex</div>
        <div className="zara-header-greeting-subtitle">Tudo pronto — é só falar.</div>
      </div>
      <div className="zara-header-spacer" />
      <div className="zara-header-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="11" cy="11" r="7"/>
          <path d="m20 20-3.6-3.6"/>
        </svg>
        <span>Buscar</span>
      </div>
      <div className="zara-header-notifications">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
          <path d="M18 8.5a6 6 0 1 0-12 0c0 6-2.5 7.5-2.5 7.5h17S18 14.5 18 8.5Z"/>
          <path d="M13.7 19.5a2 2 0 0 1-3.4 0"/>
        </svg>
        <div className="zara-header-notifications-badge" />
      </div>
      <div className="zara-header-user">
        <span className="zara-header-user-name">Alex</span>
        <div className="zara-header-user-avatar" />
      </div>
    </header>
  );
};