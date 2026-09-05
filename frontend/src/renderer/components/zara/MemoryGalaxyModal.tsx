import React, { useEffect, useMemo, useState } from 'react';
import { X, Network, CircleDot, RefreshCw } from 'lucide-react';

interface Props { onClose: () => void; }
interface MemoryNode { id: string; kind: 'project' | 'user' | 'context' | 'history'; title: string; content: string; source: string; }
const LABELS: Record<MemoryNode['kind'], string> = { project: 'Projeto', user: 'Usuário', context: 'Contexto', history: 'Histórico' };

export const MemoryGalaxyModal: React.FC<Props> = ({ onClose }) => {
  const [nodes, setNodes] = useState<MemoryNode[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = async () => {
    await Promise.resolve();
    setLoading(true); setError('');
    try {
      const response = await window.zaraIPC?.memoryGalaxy?.list?.();
      if (!response?.success || !Array.isArray(response.nodes)) throw new Error('Fonte de memória indisponível');
      setNodes(response.nodes);
      setSelectedId((current) => response.nodes.some((node: MemoryNode) => node.id === current) ? current : (response.nodes[0]?.id || ''));
    } catch (err) {
      setNodes([]); setSelectedId(''); setError(err instanceof Error ? err.message : 'Não foi possível ler as memórias');
    } finally { setLoading(false); }
  };
  // load yields before updating state, so the effect never performs a synchronous state update.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, []);
  const selected = useMemo(() => nodes.find((node) => node.id === selectedId), [nodes, selectedId]);
  return <div className="modal-backdrop" onMouseDown={(e) => e.currentTarget === e.target && onClose()}>
    <section className="galaxy-modal" role="dialog" aria-modal="true" aria-label="Memory Galaxy">
      <header><div><Network size={17}/><span>MEMORY GALAXY · MEMÓRIAS REAIS</span></div><button onClick={onClose} aria-label="Fechar"><X size={17}/></button></header>
      <div className="galaxy-real-layout">
        <nav aria-label="Memórias disponíveis">
          {loading && <div className="galaxy-state">Lendo fontes locais…</div>}
          {!loading && error && <div className="galaxy-state error">{error}</div>}
          {!loading && !error && nodes.length === 0 && <div className="galaxy-state">Nenhuma memória real encontrada.</div>}
          {nodes.map((node) => <button key={node.id} className={node.id === selectedId ? 'selected' : ''} onClick={() => setSelectedId(node.id)}>
            <i className={`memory-kind ${node.kind}`}/><span><strong>{node.title}</strong><small>{LABELS[node.kind]} · {node.source}</small></span>
          </button>)}
        </nav>
        <article aria-live="polite">{selected ? <><span className="galaxy-source">{LABELS[selected.kind]} · {selected.source}</span><h3>{selected.title}</h3><pre>{selected.content}</pre></> : <div className="galaxy-state">Selecione uma memória para inspecionar.</div>}</article>
      </div>
      <footer><span><CircleDot size={14}/> {nodes.length} ITENS REAIS</span><span>{error ? 'LEITURA INDISPONÍVEL' : 'PROJECT · USER · CONTEXT/HISTORY'}</span><button onClick={() => void load()} disabled={loading}><RefreshCw size={13}/> Atualizar</button></footer>
    </section>
  </div>;
};
