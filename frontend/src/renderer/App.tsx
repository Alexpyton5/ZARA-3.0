import React from 'react';
import { RendererErrorBoundary } from './components/RendererErrorBoundary';
import { ZaraHome } from './components/zara-home/ZaraHome';

// ZARA-HOME-INTEGRACAO-001: a Home Titanium Emerald deixou de ser um iframe
// carregando um build estático separado (frontend/public/zara-titanium-emerald/)
// e passou a ser componentes React reais, conectados ao IPC/backend
// existente. Ver ZARA_HOME_UI_INTEGRATION.md.
const App: React.FC = () => (
  <RendererErrorBoundary>
    <div style={{ width: '100vw', height: '100vh', background: '#000' }}>
      <ZaraHome />
    </div>
  </RendererErrorBoundary>
);

export default App;
