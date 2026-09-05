import React, { useEffect, useMemo, useState } from 'react';

// MEMORY-GALAXY-VIEW-001 (Alex, 2026-08-27): o grafo de memoria mora DENTRO da
// tela da Zara agora, nao mais no Obsidian externo. O componente antigo
// (MemoryGalaxyModal) foi descartado nesta mesma sessao -- este e um desenho
// novo: layout circular deterministico, SVG puro (sem lib nova), sem modal.
//
// Contrato de dados (ja pronto e testado no backend, core/ipc_handlers.py
// handle_memory_galaxy_list): window.zaraIPC.memoryGalaxy.list() devolve
// { success, nodes: [{id, kind, title, content, source, updated_at}],
//   links: [{source, target}], count, sources }.

interface MemoryNode {
  id: string;
  kind: string;
  title: string;
  content: string;
  source: string;
  updated_at?: number | string;
}

interface MemoryLink {
  source: string;
  target: string;
}

interface MemoryGalaxyResponse {
  success?: boolean;
  nodes?: MemoryNode[];
  links?: MemoryLink[];
  count?: number;
  sources?: string[];
}

const RAIO = 220;
const CENTRO = 260;
const LADO = CENTRO * 2;

// Cor por tipo de memoria -- as mesmas famílias de cor que o resto da Zara
// ja usa (vinho, dourado, verde), so que aqui identificando a ORIGEM do dado,
// nao o autor de uma mensagem.
function corDoNo(kind: string): string {
  const k = (kind || '').toLowerCase();
  if (k.includes('project')) return 'var(--accent, #72586F)';
  if (k.includes('user')) return '#c8a15f';
  if (k.includes('history') || k.includes('conversation')) return 'var(--green, #6f9a6a)';
  return 'var(--muted, #85817A)';
}

function rotuloDoTipo(kind: string): string {
  const k = (kind || '').toLowerCase();
  if (k.includes('project')) return 'Projeto';
  if (k.includes('user')) return 'Usuário';
  if (k.includes('history') || k.includes('conversation')) return 'Histórico';
  if (k.includes('context')) return 'Contexto';
  return kind || 'Memória';
}

function posicao(index: number, total: number): { x: number; y: number } {
  const angulo = (index / Math.max(1, total)) * Math.PI * 2 - Math.PI / 2;
  return {
    x: CENTRO + Math.cos(angulo) * RAIO,
    y: CENTRO + Math.sin(angulo) * RAIO,
  };
}

export const MemoryGalaxyView: React.FC = () => {
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState('');
  const [nodes, setNodes] = useState<MemoryNode[]>([]);
  const [links, setLinks] = useState<MemoryLink[]>([]);
  const [selecionadoId, setSelecionadoId] = useState('');

  useEffect(() => {
    let vivo = true;
    (async () => {
      setCarregando(true);
      setErro('');
      try {
        const resposta: MemoryGalaxyResponse | undefined = await window.zaraIPC?.memoryGalaxy?.list?.();
        if (!vivo) return;
        if (!resposta || resposta.success === false) throw new Error('Fonte de memória indisponível');
        const nextNodes = Array.isArray(resposta.nodes) ? resposta.nodes : [];
        const nextLinks = Array.isArray(resposta.links) ? resposta.links : [];
        setNodes(nextNodes);
        setLinks(nextLinks);
      } catch {
        if (!vivo) return;
        setNodes([]);
        setLinks([]);
        setErro('Não consegui ler as memórias agora.');
      } finally {
        if (vivo) setCarregando(false);
      }
    })();
    return () => { vivo = false; };
  }, []);

  const posicoes = useMemo(() => {
    const mapa = new Map<string, { x: number; y: number }>();
    nodes.forEach((node, index) => mapa.set(node.id, posicao(index, nodes.length)));
    return mapa;
  }, [nodes]);

  const selecionado = useMemo(
    () => nodes.find((node) => node.id === selecionadoId) || null,
    [nodes, selecionadoId],
  );

  return (
    <div className="memory-galaxy-view" style={estilos.container}>
      <header style={estilos.cabecalho}>
        <strong style={estilos.titulo}>Galáxia de memória</strong>
        <span style={estilos.contagem}>{nodes.length} {nodes.length === 1 ? 'memória' : 'memórias'}</span>
      </header>

      <div style={estilos.corpo}>
        <div style={estilos.palco}>
          {carregando ? (
            <p style={estilos.mensagemEstado}>Lendo as memórias...</p>
          ) : erro ? (
            <p style={{ ...estilos.mensagemEstado, ...estilos.mensagemErro }}>{erro}</p>
          ) : nodes.length === 0 ? (
            <p style={estilos.mensagemEstado}>Nenhuma memória encontrada ainda.</p>
          ) : (
            <svg viewBox={`0 0 ${LADO} ${LADO}`} role="img" aria-label="Grafo de memória" style={estilos.svg}>
              {links.map((link, index) => {
                const a = posicoes.get(link.source);
                const b = posicoes.get(link.target);
                if (!a || !b) return null;
                return (
                  <line
                    key={`${link.source}-${link.target}-${index}`}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke="var(--line, rgba(36,35,33,.18))"
                    strokeWidth={1}
                  />
                );
              })}
              {nodes.map((node) => {
                const p = posicoes.get(node.id);
                if (!p) return null;
                const ativo = node.id === selecionadoId;
                return (
                  <g
                    key={node.id}
                    transform={`translate(${p.x}, ${p.y})`}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelecionadoId(node.id)}
                    role="button"
                    aria-label={node.title || node.id}
                  >
                    <circle
                      r={ativo ? 11 : 8}
                      fill={corDoNo(node.kind)}
                      stroke={ativo ? 'var(--ink, #242321)' : 'transparent'}
                      strokeWidth={2}
                    />
                    <text
                      y={22}
                      textAnchor="middle"
                      fontSize={10}
                      fill="var(--muted, #85817A)"
                      style={{ pointerEvents: 'none' }}
                    >
                      {(node.title || node.id).slice(0, 18)}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </div>

        <aside style={estilos.painelLateral} aria-live="polite">
          {selecionado ? (
            <>
              <span style={estilos.fonteSelecionada}>{rotuloDoTipo(selecionado.kind)} · {selecionado.source}</span>
              <h3 style={estilos.tituloSelecionado}>{selecionado.title}</h3>
              <pre style={estilos.conteudoSelecionado}>{selecionado.content}</pre>
            </>
          ) : (
            <p style={estilos.mensagemEstado}>
              {nodes.length === 0 ? 'Sem memórias para mostrar.' : 'Clique em um ponto do grafo para ver o conteúdo.'}
            </p>
          )}
        </aside>
      </div>
    </div>
  );
};

const estilos: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    height: '100%',
    minHeight: 0,
    color: 'var(--ink, #242321)',
  },
  cabecalho: {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  titulo: { fontSize: 15 },
  contagem: { fontSize: 12, color: 'var(--muted, #85817A)' },
  corpo: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) 280px',
    gap: 16,
    flex: 1,
    minHeight: 0,
  },
  palco: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 0,
    border: '1px solid var(--line, rgba(36,35,33,.10))',
    borderRadius: 14,
    background: 'var(--card, #EDE9E2)',
    overflow: 'auto',
  },
  svg: { width: '100%', height: '100%', maxWidth: 560, maxHeight: 560 },
  painelLateral: {
    border: '1px solid var(--line, rgba(36,35,33,.10))',
    borderRadius: 14,
    background: 'var(--window, #FAF8F4)',
    padding: 14,
    minHeight: 0,
    overflow: 'auto',
  },
  fonteSelecionada: { fontSize: 11, color: 'var(--muted, #85817A)', textTransform: 'uppercase', letterSpacing: 0.4 },
  tituloSelecionado: { margin: '6px 0 10px', fontSize: 14 },
  conteudoSelecionado: { whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12.5, lineHeight: 1.5, color: 'var(--ink, #242321)', fontFamily: 'inherit' },
  mensagemEstado: { color: 'var(--muted, #85817A)', fontSize: 13, textAlign: 'center', padding: '0 16px' },
  mensagemErro: { color: '#b5705f' },
};
