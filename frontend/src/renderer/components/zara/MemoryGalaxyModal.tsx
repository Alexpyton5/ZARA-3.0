import React from 'react';
import { X, Network, CircleDot, ExternalLink } from 'lucide-react';

interface Props { onClose: () => void; }

const nodes = [
  ['ZARA', 50, 48, 9], ['Projects', 24, 29, 6], ['Preferences', 42, 22, 5],
  ['Sessions', 68, 25, 6], ['Knowledge', 78, 48, 7], ['People', 28, 58, 5],
  ['Automation', 43, 74, 6], ['Insights', 67, 72, 5], ['Identity', 55, 33, 5],
];

export const MemoryGalaxyModal: React.FC<Props> = ({ onClose }) => (
  <div className="modal-backdrop" onMouseDown={(e) => e.currentTarget === e.target && onClose()}>
    <section className="galaxy-modal" role="dialog" aria-modal="true" aria-label="Galaxy Memory">
      <header>
        <div><Network size={17} /><span>GALAXY MEMORY</span></div>
        <button onClick={onClose} aria-label="Fechar"><X size={17} /></button>
      </header>
      <div className="galaxy-stage">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {nodes.slice(1).map((n, i) => <line key={i} x1="50" y1="48" x2={n[1]} y2={n[2]} />)}
          {[[1,2],[2,4],[4,7],[7,6],[6,5],[5,1],[3,4]].map(([a,b], i) => <line key={`e${i}`} x1={nodes[a][1]} y1={nodes[a][2]} x2={nodes[b][1]} y2={nodes[b][2]} />)}
        </svg>
        {nodes.map(([name, x, y, size]) => (
          <div className={`galaxy-node ${name === 'ZARA' ? 'root' : ''}`} key={String(name)} style={{ left: `${x}%`, top: `${y}%` }}>
            <i style={{ width: `${size}px`, height: `${size}px` }} /><span>{name}</span>
          </div>
        ))}
      </div>
      <footer>
        <span><CircleDot size={14} /> VISUALIZAÇÃO DO GRAFO</span>
        <span className="integration-pending">OBSIDIAN • AGUARDANDO INTEGRAÇÃO REAL</span>
        <button disabled title="Será habilitado quando o backend Obsidian estiver conectado"><ExternalLink size={13}/> Abrir Obsidian</button>
      </footer>
    </section>
  </div>
);
