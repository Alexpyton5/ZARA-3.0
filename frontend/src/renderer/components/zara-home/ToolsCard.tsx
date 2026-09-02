
import vscode from '../../../assets/zara-home/brands/vscode.svg';
import postman from '../../../assets/zara-home/brands/postman.svg';
import docker from '../../../assets/zara-home/brands/docker.svg';

const TOOLS = [
  { name: 'VS Code', icon: vscode },
  { name: 'Postman', icon: postman },
  { name: 'Docker', icon: docker },
];

/**
 * "Abrir" cada ferramenta é uma ação real do sistema (abrir um app), não
 * um mock — usa `window.zaraIPC.action.execute('os_app', {...})`, o MESMO
 * canal de ações que o resto da ZARA já usa. Sem app allowlisted
 * correspondente (verificado em core/actions/os_ops.py::_SAFE_WINDOWS_APPS),
 * o próprio backend recusa com uma mensagem clara — não fingimos sucesso
 * aqui na UI.
 */
export function ToolsCard() {
  async function open(name: string) {
    if (!window.zaraIPC?.action?.execute) return;
    await window.zaraIPC.action.execute('os_app', { app: name.toLowerCase().replace(/\s+/g, '_') });
  }

  return (
    <section className="zh-section zh-glass-panel" aria-label="Ferramentas">
      <h2>Ferramentas</h2>
      {TOOLS.map((tool) => (
        <div className="zh-tool-row" key={tool.name}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <img src={tool.icon} alt="" /> {tool.name}
          </span>
          <button className="zh-tool-open" type="button" onClick={() => open(tool.name)}>
            Abrir
          </button>
        </div>
      ))}
    </section>
  );
}
