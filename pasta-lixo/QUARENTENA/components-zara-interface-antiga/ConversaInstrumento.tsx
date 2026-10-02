import React, { useEffect, useMemo, useState } from 'react';
import type { ChatMessage } from '../../lib/chatHistory';
import type { VoiceState } from './VoiceParticleSphere';
import '../../styles/instrumento.css';

type SeloTurno = 'verificado' | 'nao-verificado' | 'nao-consegui' | 'conversa';

interface MensagemComSelo extends ChatMessage {
  selo?: string;
}

interface TurnoInstrumento {
  id: string;
  falado: string;
  feito: string;
  selo: SeloTurno;
  inicio?: number;
  fim?: number;
}

interface UltimoValor {
  nome: 'VOLUME' | 'BRILHO';
  valor: number;
}

interface Props {
  mensagens: readonly MensagemComSelo[];
  estado: VoiceState;
  nivelVoz: number;
  historicoPronto: boolean;
}

const ROTULOS_ESTADO: Partial<Record<VoiceState, string>> = {
  LISTENING: 'OUVINDO',
  THINKING: 'PENSANDO',
  PROCESSING: 'EXECUTANDO',
  SPEAKING: 'FALANDO',
  IDLE: 'EM ESPERA',
  STANDBY: 'EM ESPERA',
};

const normalizarTexto = (texto: string): string =>
  texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

const lerSelo = (mensagem?: MensagemComSelo): SeloTurno => {
  if (!mensagem || typeof mensagem.selo !== 'string') return 'nao-verificado';
  const selo = normalizarTexto(mensagem.selo).replace(/[\s_]+/g, '-');
  if (selo === 'verificado') return 'verificado';
  if (selo === 'nao-consegui' || selo === 'falha' || selo === 'erro') return 'nao-consegui';
  if (selo === 'conversa') return 'conversa';
  return 'nao-verificado';
};

const montarTurnos = (mensagens: readonly MensagemComSelo[]): TurnoInstrumento[] => {
  const turnos: TurnoInstrumento[] = [];
  let falaPendente: MensagemComSelo | undefined;

  mensagens.forEach((mensagem, indice) => {
    if (mensagem.role === 'user') {
      if (falaPendente) {
        turnos.push({
          id: falaPendente.id ?? `${falaPendente.timestamp}-${indice}-pendente`,
          falado: falaPendente.content,
          feito: 'SEM RETORNO DA MÁQUINA',
          selo: 'nao-verificado',
          inicio: falaPendente.timestamp,
        });
      }
      falaPendente = mensagem;
      return;
    }

    turnos.push({
      id: mensagem.id ?? `${mensagem.timestamp}-${indice}`,
      falado: falaPendente?.content ?? '—',
      feito: mensagem.content,
      // Sem campo `selo`, a tela não transforma texto persuasivo em prova.
      selo: lerSelo(mensagem),
      inicio: falaPendente?.timestamp,
      fim: mensagem.timestamp,
    });
    falaPendente = undefined;
  });

  if (falaPendente) {
    turnos.push({
      id: falaPendente.id ?? `${falaPendente.timestamp}-pendente-final`,
      falado: falaPendente.content,
      feito: 'SEM RETORNO DA MÁQUINA',
      selo: 'nao-verificado',
      inicio: falaPendente.timestamp,
    });
  }

  return turnos;
};

const calcularLatenciaMediana = (turnos: readonly TurnoInstrumento[]): number | null => {
  const amostras = turnos
    .map((turno) => turno.inicio && turno.fim ? turno.fim - turno.inicio : 0)
    .filter((duracao) => duracao > 0 && duracao <= 120_000)
    .sort((a, b) => a - b);
  if (amostras.length === 0) return null;
  const meio = Math.floor(amostras.length / 2);
  return amostras.length % 2 === 0
    ? Math.round((amostras[meio - 1] + amostras[meio]) / 2)
    : Math.round(amostras[meio]);
};

const extrairUltimoValor = (mensagens: readonly MensagemComSelo[]): UltimoValor | null => {
  const ultimaResposta = [...mensagens].reverse().find((mensagem) => mensagem.role !== 'user');
  if (!ultimaResposta) return null;
  const texto = normalizarTexto(ultimaResposta.content);
  if (/\b(nao consegui|nao foi possivel|falhou|erro)\b/.test(texto)) return null;

  const depoisDoNome = texto.match(/\b(volume|brilho)\b[^0-9]{0,48}(\d{1,3})(?:[.,]\d+)?\s*%?/);
  const antesDoNome = texto.match(/(\d{1,3})(?:[.,]\d+)?\s*%?[^a-z0-9]{0,16}\b(volume|brilho)\b/);
  const nome = depoisDoNome?.[1] ?? antesDoNome?.[2];
  const numero = Number(depoisDoNome?.[2] ?? antesDoNome?.[1]);
  if ((nome !== 'volume' && nome !== 'brilho') || !Number.isFinite(numero) || numero < 0 || numero > 100) {
    return null;
  }
  // O número é somente o valor informado no retorno; o selo continua vindo
  // exclusivamente do dado estruturado e nunca desta leitura textual.
  return { nome: nome.toUpperCase() as UltimoValor['nome'], valor: Math.round(numero) };
};

const formatarHora = (agora: number): string =>
  new Date(agora).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export const ConversaInstrumento: React.FC<Props> = ({
  mensagens,
  estado,
  nivelVoz,
  historicoPronto,
}) => {
  const [agora, setAgora] = useState<number | null>(null);
  const turnos = useMemo(() => montarTurnos(mensagens), [mensagens]);
  const latencia = useMemo(() => calcularLatenciaMediana(turnos), [turnos]);
  const ultimoValor = useMemo(() => extrairUltimoValor(mensagens), [mensagens]);
  const nivelSeguro = Math.max(0, Math.min(1, nivelVoz));
  const barrasAtivas = Math.round(nivelSeguro * 7);

  useEffect(() => {
    const relogio = window.setInterval(() => setAgora(Date.now()), 1_000);
    return () => window.clearInterval(relogio);
  }, []);

  return (
    <section className="instrumento" aria-label="Interface instrumental da ZARA">
      <header className="instrumento-estado">
        <div className="instrumento-nivel" aria-label={`Nível de voz ${Math.round(nivelSeguro * 100)}%`}>
          {[0, 1, 2, 3, 4, 5, 6].map((barra) => (
            <i
              aria-hidden="true"
              className={barra < barrasAtivas ? 'ativa' : ''}
              key={barra}
              style={{ height: `${7 + Math.round(nivelSeguro * (9 + ((barra * 5) % 13)))}px` }}
            />
          ))}
        </div>
        <strong>ZARA</strong>
        <span className="instrumento-estado-atual">{ROTULOS_ESTADO[estado] ?? 'EM ESPERA'}</span>
        <div className="instrumento-telemetria">
          <time dateTime={agora === null ? undefined : new Date(agora).toISOString()}>
            {agora === null ? '—:—' : formatarHora(agora)}
          </time>
          <span>LATÊNCIA MEDIANA {latencia === null ? '—' : `${latencia} MS`}</span>
        </div>
      </header>

      {ultimoValor && (
        <section className="instrumento-valor" aria-label={`Último valor informado: ${ultimoValor.nome} ${ultimoValor.valor}%`}>
          <div>
            <span>ÚLTIMO VALOR · {ultimoValor.nome}</span>
            <strong>{ultimoValor.valor}<small>%</small></strong>
          </div>
          <div className="instrumento-escala" aria-hidden="true">
            {Array.from({ length: 20 }, (_, indice) => (
              <i className={indice < Math.round(ultimoValor.valor / 5) ? 'ativa' : ''} key={indice}/>
            ))}
          </div>
        </section>
      )}

      <section className="instrumento-registro" aria-labelledby="instrumento-registro-titulo">
        <header>
          <strong id="instrumento-registro-titulo">REGISTRO DE TURNOS</strong>
          <span>FALADO / FEITO / SELO</span>
        </header>
        <div className="instrumento-turnos">
          {turnos.length === 0 && (
            <p className="instrumento-vazio" role="status">
              {historicoPronto
                ? 'OUVINDO · À ESPERA DO PRIMEIRO PEDIDO'
                : 'OUVINDO · PREPARANDO O REGISTRO'}
            </p>
          )}
          {[...turnos].reverse().map((turno) => (
            <article className="instrumento-turno" key={turno.id}>
              <blockquote>“{turno.falado}”</blockquote>
              <p>{turno.feito}</p>
              {turno.selo !== 'conversa' && (
                <span className={`instrumento-selo selo-${turno.selo}`}>
                  {turno.selo === 'verificado'
                    ? 'VERIFICADO'
                    : turno.selo === 'nao-consegui'
                      ? 'NÃO CONSEGUI'
                      : 'NÃO VERIFICADO'}
                </span>
              )}
            </article>
          ))}
        </div>
      </section>
    </section>
  );
};
