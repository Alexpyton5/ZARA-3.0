import React from 'react';
import { RendererErrorBoundary } from './components/RendererErrorBoundary';
import { ZaraHome } from './components/zara-home/ZaraHome';

const App: React.FC = () => (
  <RendererErrorBoundary>
    <div style={{ width: '100vw', height: '100vh', background: '#000' }}>
      <ZaraHome />
    </div>
  </RendererErrorBoundary>
);

export default App;
