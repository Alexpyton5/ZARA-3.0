import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ComputerAgentOverlay } from './components/computer-agent/ComputerAgentOverlay';
import './styles/globals.css';
import './styles/zara-nova.css';

// Janela de overlay do use-computer (Frente B): o main process abre esta mesma
// página do renderer numa BrowserWindow fullscreen transparente passando
// `?overlay=computer-agent` na URL (ver CONTRATO-FRENTE-C.md na pasta
// components/computer-agent). Nesse modo renderiza SÓ a borda + selo.
const overlayMode = new URLSearchParams(window.location.search).get('overlay') === 'computer-agent';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {overlayMode ? <ComputerAgentOverlay /> : <App />}
  </React.StrictMode>,
);

// If the module graph loaded and React mounted, remove the HTML-level boot
// diagnostic. If an import fails before this point, the user sees a useful
// loading/failure clue instead of a completely black window.
document.getElementById('boot-diagnostic')?.remove();
