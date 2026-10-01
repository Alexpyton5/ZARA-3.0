/** Tela Início: quem está cuidando do computador, o que está em andamento,
 *  o que já foi entregue e o que precisa de decisão — mais o controle de pausar.
 *  Princípio: ajudar o Alex a confiar que pode sair sem acompanhar tudo.
 *
 *  ADENDO: porcentagens e animações só representam capacidades reais —
 *  por isso os itens mostram estado (em andamento / pausado / entregue),
 *  nunca barra de progresso inventada. */

import { MessageCircle, Pause, Play, Check, User, CircleQuestionMark } from 'lucide-react';
import type { CuidandoInfo, TrabalhoItem, DecisaoItem, AvatarInfo } from './types';
import officeHero from '../../assets/prototipo/core-office.webp';

export interface InicioProps {
  cuidando: CuidandoInfo;
  emAndamento: TrabalhoItem[];
  entregas: TrabalhoItem[];
  decisoes: DecisaoItem[];
  onPausar: () => void;
  /** true = equipe pausada (a fiação real informa). */
  pausado?: boolean;
  pausando?: boolean;
  estadoConfirmado?: boolean;
  pilotoConectado?: boolean;
  pilotoCarregando?: boolean;
  pilotoErro?: boolean;
  /** Ir para a conversa (opcional; o shell pode passar). */
  onConversar?: () => void;
  /** Abrir o escritório ilustrado (opcional). */
  onVerOffice?: () => void;
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
  pausando = false,
  estadoConfirmado = false,
  pilotoConectado = false,
  pilotoCarregando = true,
  pilotoErro = false,
  onConversar,
  onVerOffice,
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
            {estadoConfirmado
              ? pausado ? 'A equipe está pausada. Você pode retomar quando quiser.'
                : emAndamento.length ? `A equipe tem ${emAndamento.length} trabalho${emAndamento.length === 1 ? '' : 's'} em andamento. Veja as atualizações quando voltar.`
                  : 'A equipe está disponível. Diga o que você quer realizar.'
              : 'Confirmando a conexão e o estado da equipe…'}
          </p>
          {onConversar ? (
            <button type="button" className="primary-button" onClick={onConversar}>
              <MessageCircle size={16} aria-hidden="true" />
              Conversar com {cuidando.avatar.nome}
            </button>
          ) : null}
        </div>

        <div className="home-office-preview">
          <div className="office-scene">
            {cuidando.avatar.id === 'alfred' ? <div className="pilot-home-presence"><AvatarMini avatar={cuidando.avatar} size={142} /><strong>Seu tempo, de volta.</strong><span>Uma conversa para conduzir. Uma equipe para realizar.</span></div> : <img
              className="office-original"
              src={officeHero}
              alt="Escritório — a equipe reunida"
            />}
          </div>
          {onVerOffice ? (
            <button type="button" className="preview-button" onClick={onVerOffice}>
              {cuidando.avatar.id === 'alfred' ? 'Ver minha equipe' : 'Ver o escritório'}
            </button>
          ) : null}
        </div>
      </section>

      <section className="confidence-grid">
        <div className="confidence-card">
          <div className="card-heading">
            <h2>Seu piloto</h2>
            <button
              type="button"
              className="secondary-button"
              onClick={onPausar}
              disabled={pausando || !estadoConfirmado}
              aria-pressed={pausado}
              title={pausado ? 'Retomar o trabalho da equipe' : 'Pausar o trabalho da equipe'}
            >
              {pausado ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
              {pausando ? 'Aguardando…' : pausado ? 'Retomar equipe' : 'Pausar equipe'}
            </button>
          </div>
          <div className="task-row" role="listitem">
            <AvatarMini avatar={cuidando.avatar} size={44} />
            <div className="task-copy">
              <strong>{cuidando.avatar.nome}</strong>
              <span>{cuidando.avatar.papel}</span>
              <span>
                {pilotoCarregando ? 'Conferindo a conta…'
                  : pilotoErro ? 'Não foi possível verificar a conta.'
                    : pilotoConectado ? 'Conta conectada.' : 'Conecte a conta para conversar com seu piloto.'}
              </span>
            </div>
          </div>
          <p className="pilot-card-note">{pausado
            ? 'A equipe está pausada. Comandos diretos no computador são controlados separadamente.'
            : !estadoConfirmado ? 'Estado da equipe ainda não confirmado.'
              : `${emAndamento.length} trabalho${emAndamento.length === 1 ? '' : 's'} em andamento na equipe.`}</p>
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
            A ideia por trás da TROPA dev.
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
