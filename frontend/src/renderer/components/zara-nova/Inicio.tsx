/** Tela Início: quem está cuidando do computador, o que está em andamento,
 *  o que já foi entregue e o que precisa de decisão — mais o controle de pausar.
 *  Princípio: ajudar o Alex a confiar que pode sair sem acompanhar tudo.
 *
 *  ADENDO: porcentagens e animações só representam capacidades reais —
 *  por isso os itens mostram estado (em andamento / pausado / entregue),
 *  nunca barra de progresso inventada. */

import { MessageCircle, Pause, Play, Check, User, CircleQuestionMark } from 'lucide-react';
import type { CuidandoInfo, TrabalhoItem, DecisaoItem, AvatarInfo } from './types';

export interface InicioProps {
  cuidando: CuidandoInfo;
  emAndamento: TrabalhoItem[];
  entregas: TrabalhoItem[];
  decisoes: DecisaoItem[];
  onPausar: () => void;
  /** true = equipe pausada (a fiação real informa). */
  pausado?: boolean;
  /** Ir para a conversa (opcional; o shell pode passar). */
  onConversar?: () => void;
  /** Registrar a escolha numa decisão (opcional; fiação real). */
  onDecidir?: (decisaoId: string, opcao: string) => void;
}

function AvatarMini({ avatar, size = 39 }: { avatar: AvatarInfo; size?: number }) {
  if (avatar.imagemUrl) {
    return (
      <span className="avatar" style={{ width: size, height: size }}>
        <img src={avatar.imagemUrl} alt={avatar.nome} loading="lazy" />
      </span>
    );
  }
  return (
    <span className="avatar pending-avatar" style={{ width: size, height: size }} aria-label={avatar.nome}>
      <User size={Math.round(size * 0.45)} aria-hidden="true" />
    </span>
  );
}

const ESTADO_ROTULO: Record<TrabalhoItem['estado'], string> = {
  andamento: 'Em andamento',
  entregue: 'Entregue',
  pausado: 'Pausado',
};

function LinhaTrabalho({ item }: { item: TrabalhoItem }) {
  return (
    <div className="task-row" role="listitem">
      <AvatarMini avatar={item.responsavel} />
      <div className="task-copy">
        <strong>{item.titulo}</strong>
        <span>
          {item.responsavel.nome} · {item.responsavel.papel}
        </span>
        {item.descricao ? <span>{item.descricao}</span> : null}
      </div>
      <span className="task-percent">{ESTADO_ROTULO[item.estado]}</span>
    </div>
  );
}

export function Inicio({
  cuidando,
  emAndamento,
  entregas,
  decisoes,
  onPausar,
  pausado = false,
  onConversar,
  onDecidir,
}: InicioProps) {
  return (
    <>
      <section className="home-greeting">
        <div className="home-message">
          <span className="home-kicker">PENSA E FAZ</span>
          <h2>
            Você vive.
            <br />A equipe cuida.
          </h2>
          <p>
            {cuidando.avatar.nome} está {cuidando.supervisionado ? 'de olho no seu computador agora' : 'cuidando sozinha'}
            . Saia tranquilo: o trabalho continua e você vê tudo aqui quando voltar.
          </p>
          {onConversar ? (
            <button type="button" className="primary-button" onClick={onConversar}>
              <MessageCircle size={16} aria-hidden="true" />
              Conversar com {cuidando.avatar.nome}
            </button>
          ) : null}
        </div>

        <div className="home-office-preview" aria-hidden="true">
          <div className="office-scene" />
        </div>
      </section>

      <section className="confidence-grid">
        <div className="confidence-card">
          <div className="card-heading">
            <h2>Quem está cuidando</h2>
            <button
              type="button"
              className="secondary-button"
              onClick={onPausar}
              aria-pressed={pausado}
              title={pausado ? 'Retomar o trabalho da equipe' : 'Pausar o trabalho da equipe'}
            >
              {pausado ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
              {pausado ? 'Retomar' : 'Pausar'}
            </button>
          </div>
          <div className="task-row" role="listitem">
            <AvatarMini avatar={cuidando.avatar} size={44} />
            <div className="task-copy">
              <strong>{cuidando.avatar.nome}</strong>
              <span>{cuidando.avatar.papel}</span>
              <span>
                {pausado
                  ? 'Trabalho pausado por você.'
                  : cuidando.supervisionado
                    ? 'Com o supercérebro ligado — você está olhando.'
                    : 'Operando sozinha, com segurança.'}
                {cuidando.desde ? ` Desde ${cuidando.desde}.` : ''}
              </span>
            </div>
          </div>
        </div>

        <div className="confidence-card">
          <div className="card-heading">
            <h2>Em andamento</h2>
            <span className="subtle-badge">{emAndamento.length}</span>
          </div>
          {emAndamento.length > 0 ? (
            <div role="list">
              {emAndamento.map((item) => (
                <LinhaTrabalho key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <p className="empty-hint">Nada em andamento agora. A equipe está à disposição.</p>
          )}
        </div>

        <div className="confidence-card">
          <div className="card-heading">
            <h2>Entregas</h2>
          </div>
          {entregas.length > 0 ? (
            <div role="list">
              {entregas.map((item) => (
                <div className="done-row" role="listitem" key={item.id}>
                  <span className="done-check" aria-hidden="true">
                    <Check size={14} />
                  </span>
                  <div>
                    <strong>{item.titulo}</strong>
                    <span>{item.responsavel.nome}</span>
                  </div>
                  <time>{item.atualizadoEm}</time>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-hint">Nenhuma entrega ainda. Quando a equipe concluir algo, aparece aqui.</p>
          )}
        </div>

        <div className="confidence-card">
          <div className="card-heading">
            <h2>Precisa de decisão</h2>
            <span className="subtle-badge">{decisoes.length}</span>
          </div>
          {decisoes.length > 0 ? (
            <div role="list">
              {decisoes.map((d) => (
                <div className="decisao-row" role="listitem" key={d.id}>
                  <span className="done-check" aria-hidden="true">
                    <CircleQuestionMark size={14} />
                  </span>
                  <div className="decisao-copy">
                    <strong>{d.pergunta}</strong>
                    <span>{d.contexto}</span>
                    <div className="suggestions">
                      {d.opcoes.map((opcao) => (
                        <button
                          key={opcao}
                          type="button"
                          onClick={() => onDecidir?.(d.id, opcao)}
                          disabled={!onDecidir}
                          title={onDecidir ? undefined : 'A decisão será registrada na etapa de fiação.'}
                        >
                          {opcao}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-hint">Nada esperando sua decisão. Pode relaxar.</p>
          )}
        </div>
      </section>

      <section className="home-bottom">
        <details className="official-story">
          <summary>
            A ideia por trás da ZARA
          </summary>
          <blockquote>
            “O Muse AI é tipo um Power Ranger. Ele é foda — inteligente pra caramba, conversa, pensa, resolve. Mas
            ele não tem braços e pernas: ele não abre seus arquivos, não mexe no seu computador, não faz nada no
            mundo real.
            <br />
            <br />
            O meu app é o que dá braços e pernas pra ele. O Muse continua sendo o cérebro — e o app vira o corpo:
            voz, visão, memória e controle total do PC. Juntos, eles viram o Ranger completo: pensa E faz.”
          </blockquote>
          <p>A visão do Alex para o app.</p>
        </details>
      </section>
    </>
  );
}
