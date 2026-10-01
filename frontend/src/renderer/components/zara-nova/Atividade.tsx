import { Check, ExternalLink } from 'lucide-react';
import type { AtividadeItem, AvatarInfo } from './types';

interface AtividadeProps {
  itens: AtividadeItem[];
  /** Quando true, mostra o estado honesto de carregamento. */
  carregando?: boolean;
  onAbrirEntrega: (item: AtividadeItem) => void;
}

/** Rosto do avatar: foto quando existe, inicial estilizada quando não. */
function AvatarRosto({ avatar, tamanho = 47 }: { avatar: AvatarInfo; tamanho?: number }) {
  if (avatar.imagemUrl) {
    return (
      <span className="avatar" style={{ width: tamanho, height: tamanho }}>
        <img src={avatar.imagemUrl} alt={avatar.nome} loading="lazy" />
      </span>
    );
  }
  const iniciais = avatar.nome.trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '·';
  return (
    <span className="avatar pending-avatar" style={{ width: tamanho, height: tamanho }} aria-hidden="true">
      {iniciais}
    </span>
  );
}

/**
 * Atividade — "Enquanto você estava fora".
 * Resumo do que foi concluído + acesso direto ao que foi produzido.
 * ADENDO #3: não existe capacidade real de desfazer, então NÃO há botão de desfazer.
 */
export function Atividade({ itens, carregando = false, onAbrirEntrega }: AtividadeProps) {
  const day = (date: Date) => date.toLocaleDateString('pt-BR', { timeZone: 'America/Bahia' });
  const today = day(new Date());
  const todayCount = itens.filter(item => day(new Date(item.concluidoEm)) === today).length;
  if (carregando) {
    return (
      <section className="activity-view" aria-label="Atividade">
        <div className="empty-panel" role="status">
          <h2>Carregando as atividades…</h2>
          <p>Buscando o que a equipe concluiu.</p>
        </div>
      </section>
    );
  }

  if (!itens.length) {
    return (
      <section className="activity-view" aria-label="Atividade">
        <div className="activity-summary">
          <div className="summary-cell">
            <span>Pronto hoje</span>
            <strong>0 entregas</strong>
          </div>
          <div className="summary-cell">
            <span>Seu tempo protegido</span>
            <strong>Você no comando</strong>
          </div>
        </div>
        <div className="empty-panel">
          <h2>Nada concluído por aqui ainda</h2>
          <p>Quando a equipe concluir um trabalho, ele aparece nesta linha do tempo — com o resultado pronto para você ver.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="activity-view" aria-label="Atividade">
      <div className="activity-summary">
        <div className="summary-cell">
          <span>Pronto hoje</span>
          <strong>{todayCount} {todayCount === 1 ? 'entrega' : 'entregas'}</strong>
        </div>
        <div className="summary-cell">
          <span>Seu tempo protegido</span>
          <strong>Você no comando</strong>
        </div>
      </div>

      <div className="timeline-label">
        ENTREGAS
          <span>· {itens.length} {itens.length === 1 ? 'entrega' : 'entregas'}</span>
      </div>

      {itens.map((item) => (
        <article className="activity-card" key={item.id}>
          <AvatarRosto avatar={item.responsavel} />
          <div className="activity-copy">
            <h3>{item.titulo}</h3>
            <p>{item.descricao}</p>
            <span className="activity-meta">
              {item.responsavel.nome} · {new Date(item.concluidoEm).toLocaleString('pt-BR', { timeZone: 'America/Bahia', dateStyle: 'short', timeStyle: 'short' })} · Concluído
            </span>
          </div>
          {item.entregavelUrl ? (
            <button type="button"
              className="secondary-button"
              onClick={() => onAbrirEntrega(item)}
            >
              <ExternalLink size={14} aria-hidden="true" />
              Ver resultado
            </button>
          ) : (
            <span className="done-check" aria-label="Concluído" title="Concluído">
              <Check size={14} aria-hidden="true" />
            </span>
          )}
        </article>
      ))}

      <p className="activity-note">
        Tudo que a equipe entrega aparece aqui, com acesso direto ao que foi produzido.
      </p>
    </section>
  );
}

export default Atividade;
