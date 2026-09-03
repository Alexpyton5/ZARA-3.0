import { PenTool } from 'lucide-react';
import vscode from '../../../assets/zara-home/brands/vscode.svg';
import postman from '../../../assets/zara-home/brands/postman.svg';
import docker from '../../../assets/zara-home/brands/docker.svg';

const TOOLS = [
  { name: 'VS Code', icon: vscode },
  { name: 'Figma', Icon: PenTool, color: '#f24e1e' },
  { name: 'Postman', icon: postman },
  { name: 'Docker', icon: docker },
];

/**
 * Ferramentas — layout do MASTER (grade 2×2 com ícone grande e rótulo
 * "Abrir"). Abrir app usa action.execute real do IPC.
 */
export function ToolsCard() {
  async function open(name: string) {
    if (!window.zaraIPC?.action?.execute) return;
    await window.zaraIPC.action.execute('os_app', { app: name.toLowerCase().replace(/\s+/g, '_') });
  }

  return (
    <section className="zh-section zh-glass-panel" aria-label="Ferramentas">
      <h2>Ferramentas</h2>
      <div className="zh-tools-grid">
        {TOOLS.map((tool) => (
          <button
            className="zh-tool-tile"
            type="button"
            key={tool.name}
            onClick={() => open(tool.name)}
          >
            {tool.icon ? (
              <img src={tool.icon} alt="" />
            ) : (
              tool.Icon && <tool.Icon size={26} strokeWidth={1.8} style={{ color: tool.color }} />
            )}
            <span className="zh-tool-name">{tool.name}</span>
            <span className="zh-tool-open">Abrir</span>
          </button>
        ))}
      </div>
    </section>
  );
}
