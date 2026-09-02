import React from 'react';

interface ZaraSidebarProps {
  onSettingsClick?: () => void;
}

export const ZaraSidebar: React.FC<ZaraSidebarProps> = ({ onSettingsClick }) => {
  return (
    <div className="zara-sidebar">
      {/* Logo */}
      <div className="zara-sidebar-logo">
        <img 
          src="/zara-interface/zara-logo-original.png" 
          alt="ZARA" 
          className="zara-sidebar-logo-img"
        />
      </div>
      
      {/* Navigation */}
      <nav className="zara-sidebar-nav" aria-label="Navegação principal">
        <button type="button" className="zara-sidebar-nav-item" aria-label="Principal">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
            <rect x="3" y="3" width="7.5" height="7.5" rx="2"/>
            <rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/>
            <rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/>
            <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>
          </svg>
        </button>
        <button type="button" className="zara-sidebar-nav-item" aria-label="Mídia">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
            <circle cx="11" cy="11" r="7"/>
            <path d="m20 20-3.6-3.6"/>
          </svg>
        </button>
        <button type="button" className="zara-sidebar-nav-item" aria-label="Trabalho">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2.5" y="4.5" width="19" height="12.5" rx="2.2"/>
            <path d="M8.5 21h7"/>
          </svg>
        </button>
        <button type="button" className="zara-sidebar-nav-item" aria-label="Casa">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
            <path d="M4 6h16M4 12h16M4 18h10"/>
          </svg>
        </button>
      </nav>
      
      {/* Spacer */}
      <div className="zara-sidebar-spacer" />
      
      {/* Settings button at the bottom */}
      <button 
        type="button" 
        className="zara-sidebar-settings"
        aria-label="Configurações"
        onClick={onSettingsClick}
      >
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3.2"/>
          <path d="M19.5 14.6a1.7 1.7 0 0 0 .34 1.87 2 2 0 1 1-2.84 2.84 1.7 1.7 0 0 0-2.9 1.21 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2 2 2 0 1 1-2.84-2.85A1.7 1.7 0 0 0 3.1 14H3a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.21-2.9 2 2 0 1 1 2.84-2.84A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.21 2 2 0 1 1 2.84 2.84A1.7 1.7 0 0 0 20.9 10H21a2 2 0 1 1 0 4z"/>
        </svg>
      </button>
    </div>
  );
};