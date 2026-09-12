import vscode from '../../../assets/zara-home/brands/vscode.svg';
import postman from '../../../assets/zara-home/brands/postman.svg';
import docker from '../../../assets/zara-home/brands/docker.svg';
import { useHomeFeedback } from './useHomeFeedback';

function FigmaGlyph() {
  // Logo oficial do Figma (5 formas nas cores da marca)
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
      <path fill="#f24e1e" d="M8 2h4v6.66H8a3.33 3.33 0 1 1 0-6.66z" />
      <path fill="#ff7262" d="M12 2h4a3.33 3.33 0 1 1 0 6.66h-4V2z" />
      <path fill="#1abcfe" d="M12 8.66a3.33 3.33 0 1 1 6.66 0 3.33 3.33 0 0 1-6.66 0z" />
      <path fill="#0acf83" d="M8 15.32h4V22H8a3.33 3.33 0 1 1 0-6.68z" />
      <path fill="#a259ff" d="M8 8.66h4v6.66H8a3.33 3.33 0 1 1 0-6.66z" />
    </svg>
  );
}

const TOOLS = [
  { name: 'VS Code', id: 'vscode' as const, icon: vscode },
  { name: 'Figma', id: 'figma' as const, Glyph: FigmaGlyph },
  { name: 'Postman', id: 'postman' as const, icon: postman },
  { name: 'Docker', id: 'docker' as const, icon: docker },
];

/**
 * Ferramentas — layout do MASTER (4 colunas planas: ícone grande, nome,
 * "Abrir"). Abrir app usa action.execute real do IPC.
 */
export function ToolsCard() {
  const { feedback, pending, run } = useHomeFeedback();

  return (
    <section className="zh-section zh-glass-panel" aria-label="Ferramentas">
      <h2>Ferramentas</h2>
      <div className="zh-tools-grid">
        {TOOLS.map((tool) => (
          <button
            className="zh-tool-tile"
            type="button"
            key={tool.name}
            onClick={() => void run(() => window.zaraIPC?.desktop?.openApp?.(tool.id), `Abertura de ${tool.name} solicitada.`)}
            disabled={pending}
            aria-label={`Abrir ${tool.name}`}
          >
            {tool.icon ? (
              <img src={tool.icon} alt="" />
            ) : (
              tool.Glyph && <tool.Glyph />
            )}
            <span className="zh-tool-name">{tool.name}</span>
            <span className="zh-tool-open">Abrir</span>
          </button>
        ))}
      </div>
      {feedback && <p className="zh-card-feedback" role="status">{feedback}</p>}
    </section>
  );
}
