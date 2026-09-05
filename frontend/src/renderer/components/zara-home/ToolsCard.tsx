import { useEffect, useState } from 'react';
import vscode from '../../../assets/zara-home/brands/vscode.svg';
import postman from '../../../assets/zara-home/brands/postman.svg';
import docker from '../../../assets/zara-home/brands/docker.svg';

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

// `id` é a chave canônica de `_SAFE_WINDOWS_APPS` — a mesma que `os_app`
// exige. Derivar do nome visível ("VS Code" -> "vs_code") funcionava por
// coincidência e quebraria no primeiro nome com acento ou pontuação.
const TOOLS = [
  { id: 'vs_code', name: 'VS Code', icon: vscode },
  { id: 'figma', name: 'Figma', Glyph: FigmaGlyph },
  { id: 'postman', name: 'Postman', icon: postman },
  { id: 'docker', name: 'Docker', icon: docker },
];

interface AppState { installed: boolean | null; running: boolean | null }

/**
 * Ferramentas — layout do MASTER (4 colunas planas: ícone grande, nome,
 * "Abrir").
 *
 * O clique chamava `action.execute('os_app', …)` e DESCARTAVA o resultado:
 * se o app não estivesse instalado, ou o executor falhasse, o botão parecia
 * ter funcionado. Agora o rótulo abaixo do nome vem de `result.output` /
 * `result.error` do executor — nunca de texto fixo — e o estado inicial
 * ("Instalado", "Aberto agora", "Não encontrado") vem de `os_app_list`, a
 * mesma lista segura que a voz usa.
 */
export function ToolsCard() {
  const execute = window.zaraIPC?.action?.execute;
  const [state, setState] = useState<Record<string, AppState>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!execute) return;
    let alive = true;
    execute('os_app_list', {})
      .then((res: { result?: { data?: { apps?: Array<{ id: string; installed: boolean | null; running: boolean | null }> } } }) => {
        const apps = res?.result?.data?.apps;
        if (!alive || !Array.isArray(apps)) return;
        const map: Record<string, AppState> = {};
        for (const a of apps) map[a.id] = { installed: a.installed, running: a.running };
        setState(map);
      })
      .catch(() => { /* sem lista: os tiles ficam em "estado desconhecido" */ });
    return () => { alive = false; };
  }, [execute]);

  function open(id: string) {
    if (!execute || busy) return;
    setBusy(id);
    execute('os_app', { app: id })
      .then((res: { result?: { success?: boolean; output?: string; error?: string } }) => {
        const r = res?.result;
        setOutcome((o) => ({
          ...o,
          [id]: r?.success ? (r.output || 'Aberto.') : (r?.error || 'Não foi possível abrir.'),
        }));
      })
      .catch((e: unknown) => setOutcome((o) => ({ ...o, [id]: e instanceof Error ? e.message : String(e) })))
      .finally(() => setBusy(null));
  }

  function rotulo(id: string): string {
    if (busy === id) return 'Abrindo…';
    if (outcome[id]) return outcome[id];
    const s = state[id];
    if (!s) return 'Abrir';
    if (s.running) return 'Aberto agora';
    if (s.installed === false) return 'Não encontrado';
    return 'Abrir';
  }

  return (
    <section className="zh-section zh-glass-panel" aria-label="Ferramentas">
      <h2>Ferramentas</h2>
      <div className="zh-tools-grid">
        {TOOLS.map((tool) => {
          const indisponivel = !execute || state[tool.id]?.installed === false;
          return (
            <button
              className="zh-tool-tile"
              type="button"
              key={tool.id}
              disabled={indisponivel || busy === tool.id}
              title={indisponivel ? `${tool.name} não encontrado neste computador` : `Abrir ${tool.name}`}
              onClick={() => open(tool.id)}
            >
              {tool.icon ? (
                <img src={tool.icon} alt="" />
              ) : (
                tool.Glyph && <tool.Glyph />
              )}
              <span className="zh-tool-name">{tool.name}</span>
              <span className="zh-tool-open">{rotulo(tool.id)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
