import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// If the module graph loaded and React mounted, remove the HTML-level boot
// diagnostic. If an import fails before this point, the user sees a useful
// loading/failure clue instead of a completely black window.
document.getElementById('boot-diagnostic')?.remove();
