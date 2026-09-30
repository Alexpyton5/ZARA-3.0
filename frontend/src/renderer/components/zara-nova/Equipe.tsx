import type { AvatarInfo, MembroEquipe, ProjetoUsuario } from './types';

interface EquipeProps {
  projetos: ProjetoUsuario[];
}

function AvatarRosto({ avatar, tamanho = 44 }: { avatar: AvatarInfo; tamanho?: number }) {
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

const STATUS_LABEL: Record<MembroEquipe['status'], string> = {
  trabalhando: 'Trabalhando',
  pausado: 'Pausado',
  disponivel: 'Disponível',
};

const STATUS_COR: Record<MembroEquipe['status'], string> = {
  trabalhando: 'var(--mint)',
  pausado: 'var(--gold)',
  disponivel: 'var(--muted)',
};

function MembroCard({ membro }: { membro: MembroEquipe }) {
  return (
    <article className="team-card">
      {membro.avatar.imagemUrl ? (
        <img src={membro.avatar.imagemUrl} alt={membro.avatar.nome} loading="lazy" />
      ) : (
        <div className="team-pending">
          <AvatarRosto avatar={membro.avatar} tamanho={56} />
          <span>Referência visual pendente</span>
        </div>
      )}
      <div className="team-card-text">
        <strong>{membro.avatar.nome}</strong>
        <small>{membro.avatar.papel}</small>
        <small>Bot customizável · sala e computador próprios</small>
        <span className="team-status">
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: STATUS_COR[membro.status],
              marginRight: 6,
            }}
          />
          {STATUS_LABEL[membro.status]}
        </span>
        {membro.tarefaAtual && (
          <span
            className="team-status"
            style={{ display: 'block', marginTop: 4 }}
            title="Tarefa atual"
          >
            {membro.tarefaAtual}
          </span>
        )}
      </div>
    </article>
  );
}

/**
 * Equipe — ADENDO #1: as salas fixas do molde NÃO são obrigatórias.
 * Os avatares se organizam conforme os PROJETOS do usuário.
 * ADENDO URGENTE: cada avatar = um bot customizável (sala + computador + especialidade próprios).
 */
export function Equipe({ projetos }: EquipeProps) {
  if (!projetos.length) {
    return (
      <section className="team-view" aria-label="Equipe">
        <p className="team-caption">
          A equipe se organiza conforme os seus projetos — não em salas fixas. Cada avatar é um bot
          customizável, com sua sala, seu computador e sua especialidade.
        </p>
        <div className="empty-panel">
          <h2>Nenhum projeto por enquanto</h2>
          <p>Quando você começar um projeto com a equipe, os avatares se organizam aqui, cada um na sua especialidade.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="team-view" aria-label="Equipe">
      <p className="team-caption">
        A equipe se organiza conforme os seus projetos — não em salas fixas. Cada avatar é um bot
        customizável, com sua sala, seu computador e sua especialidade. Cada avatar, uma especialidade.
      </p>
      {projetos.map((projeto) => (
        <section key={projeto.id} aria-label={`Projeto ${projeto.nome}`} style={{ marginBottom: 26 }}>
          <div className="card-heading">
            <h2>{projeto.nome}</h2>
            <span className="room-count" aria-label={`${projeto.membros.length} membros`}>
              {projeto.membros.length}
            </span>
          </div>
          {projeto.membros.length ? (
            <div className="team-grid">
              {projeto.membros.map((membro) => (
                <MembroCard key={membro.avatar.id} membro={membro} />
              ))}
            </div>
          ) : (
            <div className="empty-panel">
              <p>Nenhum avatar neste projeto ainda.</p>
            </div>
          )}
        </section>
      ))}
    </section>
  );
}

export default Equipe;
