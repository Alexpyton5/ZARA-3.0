import React from 'react';
import { RendererErrorBoundary } from './components/RendererErrorBoundary';
import { ZaraControlCenter } from './components/zara/ZaraControlCenter';

const App: React.FC = () => (
  <RendererErrorBoundary>
    <ZaraControlCenter />
  </RendererErrorBoundary>
);

export default App;
