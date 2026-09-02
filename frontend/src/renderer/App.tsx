import React from 'react';
import { RendererErrorBoundary } from './components/RendererErrorBoundary';

const App: React.FC = () => (
  <RendererErrorBoundary>
    <iframe
      title="ZARA — Titanium Emerald"
      src="./zara-titanium-emerald/index.html"
      allow="microphone"
      style={{
        display: 'block',
        width: '100vw',
        height: '100vh',
        border: 0,
        background: '#000',
      }}
    />
  </RendererErrorBoundary>
);

export default App;
