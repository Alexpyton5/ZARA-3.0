import { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-logo-transparent.png';
import coreGlass from '../../../assets/zara-home/core-glass.png';

interface ActiveProjectCardProps {
  onNavigate?: (section: string) => void;
}

/**
 * "Projeto ativo".
 *
 * A versão anterior era maquete inteira: "ZARA App / Desenvolvimento / 61%",
 * barra de progresso em 61%, "Última sessão: hoje, 14:12" e sete pontinhos
 * com o quarto aceso. Nenhum desses números existia — não há fonte de
 * progresso de projeto no backend, e uma barra em 61% afirma um progresso
 * medido que ninguém mediu.
 *
 * O que existe de verdade é a Project Memory (`project-memory-list` /
 * `-get`). O card passa a mostrar isso: quantos documentos existem e qual foi
 * o último atualizado. Sem Project Memory, o card diz que não há projeto
 * registrado em vez de inventar um.
 */
export function ActiveProjectCard({ onNavigate }: ActiveProjectCardProps) {
  const list = window.zaraIPC?.projectMemory?.list;
  const get = window.zaraIPC?.projectMemory?.get;
  const [state, setState] = useState<{
    loading: boolean;
    keys: string[];
    recent: { key: string; title: string; updatedAt: number | null } | null;
    error: boolean;
  }>({ loading: Boolean(list), keys: [], recent: null, error: false });

  useEffect(() => {
    if (!list) return;
    let alive = true;
    list()
      .then(async (res: { keys?: string[] }) => {
        const keys = Array.isArray(res?.keys) ? res.keys : [];
        let recent: { key: string; title: string; updatedAt: number | null } | null = null;
        if (keys.length > 0 && get) {
          // O mais recente é decidido pelo `updated_at` real dos documentos,
          // não pela ordem em que a lista voltou.
          const docs = await Promise.all(keys.slice(0, 20).map(async (k) => {
            try {
              const r = await get(k);
              const doc = (r as { doc?: { title?: string; updated_at?: number } })?.doc;
              return { key: k, title: String(doc?.title || k), updatedAt: typeof doc?.updated_at === 'number' ? doc.updated_at : null };
            } catch {
              return { key: k, title: k, updatedAt: null };
            }
          }));
          docs.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
          recent = docs[0] ?? null;
        }
        if (alive) setState({ loading: false, keys, recent, error: false });
      })
      .catch(() => { if (alive) setState({ loading: false, keys: [], recent: null, error: true }); });
    return () => { alive = false; };
  }, [list, get]);

  const temProjeto = state.recent !== null;

  return (
    <section className="zh-section zh-glass-panel" aria-label="Projeto ativo">
      <h2>Projeto ativo</h2>
      <div className="zh-project-header">
        <span className="zh-project-badge">
          <img className="zh-project-badge-glass" src={coreGlass} alt="" aria-hidden="true" />
          <img className="zh-project-badge-logo" src={zaraLogo} alt="" />
        </span>
        <div className="zh-project-meta">
          <strong>{temProjeto ? state.recent!.title : 'Nenhum projeto ativo'}</strong>
          <span>
            {!list ? 'Project Memory não conectada'
              : state.error ? 'Não foi possível ler a Project Memory'
              : state.loading ? 'Lendo…'
              : temProjeto ? `${state.keys.length} documento${state.keys.length === 1 ? '' : 's'} na Project Memory`
              : 'Nada registrado ainda'}
          </span>
        </div>
      </div>

      <div className="zh-project-row">
        <p className="zh-project-last-session">
          {temProjeto && state.recent!.updatedAt
            ? `Atualizado: ${new Date(state.recent!.updatedAt < 1e12 ? state.recent!.updatedAt * 1000 : state.recent!.updatedAt)
                .toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}`
            : temProjeto ? 'Sem data de atualização registrada' : ''}
        </p>
        <button
          className="zh-project-continue"
          type="button"
          title={temProjeto ? 'Abrir em Projetos' : 'Nenhum projeto para abrir'}
          disabled={!temProjeto}
          onClick={() => onNavigate?.('Projetos')}
        >
          Abrir
          <ChevronRight size={15} strokeWidth={2} />
        </button>
      </div>
    </section>
  );
}
