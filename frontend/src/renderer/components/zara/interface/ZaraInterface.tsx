// @ts-nocheck -- legacy experimental surface; not part of the active Titanium Emerald shell.
import React from 'react';
import '../../styles/zara-interface.css';
import { ZaraSidebar } from './ZaraSidebar';
import { ZaraHeader } from './ZaraHeader';
import { ZaraHome } from './ZaraHome';
import { ZaraMediaPanel } from './ZaraMediaPanel';
import { ZaraSystemPanel } from './ZaraSystemPanel';
import { ZaraConversationPanel } from './ZaraConversationPanel';
import { ZaraMemoryPanel } from './ZaraMemoryPanel';
import { ZaraWindowControls } from './ZaraWindowControls';

interface ZaraInterfaceProps {
  onSettingsClick?: () => void;
}

export const ZaraInterface: React.FC<ZaraInterfaceProps> = ({ onSettingsClick }) => {
  return (
    <div className="zara-interface">
      {/* Wallpaper and overlay */}
      <div className="zara-interface-background">
        <img 
          src="/zara-interface/wallpaper.jpg" 
          alt="" 
          className="zara-interface-wallpaper"
        />
        <div className="zara-interface-overlay"></div>
      </div>

      {/* Main content */}
      <div className="zara-interface-content">
        <div className="zara-interface-sidebar">
          <ZaraSidebar onSettingsClick={onSettingsClick} />
        </div>
        <div className="zara-interface-main">
          <ZaraHeader />
          <div className="zara-interface-panels">
            {/* The main panels will be rendered based on navigation */}
            <ZaraHome />
            <ZaraMediaPanel />
            <ZaraSystemPanel />
            <ZaraConversationPanel />
            <ZaraMemoryPanel />
          </div>
          <ZaraWindowControls />
        </div>
      </div>
    </div>
  );
};