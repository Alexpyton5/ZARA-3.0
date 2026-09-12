import { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-mark.svg';
import coreGlass from '../../../assets/zara-home/core-glass.png';
import { formatDate } from './homeActions';

type ProjectContext = {
  success: boolean;
  active_project_id: string | null;
  projects: Array<{ id: string; keys: string[]; updated_at: number | null }>;
  legacy_document_keys: string[];
};

export function ActiveProjectCard({ onNavigate }: { onNavigate: (section: string) => void }) {
  const [context, setContext] = useState<ProjectContext | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    if (!window.zaraIPC?.projectMemory?.context) { setLoaded(true); return; }
    window.zaraIPC.projectMemory.context()
      .then((response) => { if (!cancelled) setContext(response?.success ? response : null); })
      .catch(() => { if (!cancelled) setContext(null); })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);
  const active = context?.projects.find((project) => project.id === context.active_project_id);
  const documentCount = active?.keys.length ?? context?.legacy_document_keys.length ?? 0;
  const name = active ? (active.id.toLowerCase() === 'zara' ? 'ZARA' : active.id) : 'Nenhum projeto selecionado';
  return (
    <section className="zh-section zh-glass-panel zh-project-card" aria-label="Projeto ativo">
      <h2>Projeto ativo</h2>
      <div className="zh-project-header">
        <span className="zh-project-badge">
          <img className="zh-project-badge-glass" src={coreGlass} alt="" aria-hidden="true" />
          <img className="zh-project-badge-logo" src={zaraLogo} alt="" />
        </span>
        <div className="zh-project-meta">
          <strong>{loaded ? name : 'Consultando projeto…'}</strong>
          <span>{active ? 'Memória do projeto' : context ? 'Memória local disponível' : 'Consulte seus projetos'}</span>
          <span className="zh-project-percent">{context ? `${documentCount} ${documentCount === 1 ? 'documento' : 'documentos'}` : '—'}</span>
        </div>
      </div>
      <div className="zh-progress-track" aria-label="Progresso do projeto não informado"><div className="zh-progress-fill" style={{ width: '0%' }} /></div>
      <div className="zh-project-row">
        <p className="zh-project-last-session">{active?.updated_at ? `Atualizado: ${formatDate(active.updated_at)}` : 'Seu contexto, sempre por perto.'}</p>
        <button className="zh-project-continue" type="button" onClick={() => onNavigate('Projetos')}>{active ? 'Continuar' : 'Abrir'}<ChevronRight size={19} strokeWidth={1.7} /></button>
      </div>
      <div className="zh-project-dots" aria-hidden="true">{Array.from({ length: 7 }).map((_, index) => <span key={index} data-active={Boolean(active) && index === 3} />)}</div>
    </section>
  );
}
