/** Conversa: texto na sessao do piloto e controlador existente de voz. Sem resposta simulada. */

import { useEffect, useRef, useState } from 'react';
import { Send, Mic, MicOff, ShieldCheck, MessageCircle } from 'lucide-react';
import type { AvatarInfo } from './types';
import { avatarOriginal } from './avatares';
import { mapearEstadoVoz, type EstadoVozReal, type MotorVoz } from './Voz';
import { useToast } from './chrome/ZaraNovaShell';

export interface ConversaMensagem {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  status?: 'pending' | 'sent' | 'unknown';
}

/** Controlador do pipeline real de voz (ligado ao useZoeVoice pela FIAÇÃO). */
export interface ControladorVoz {
  estado: EstadoVozReal;
  erro?: string;
  motor?: MotorVoz;
  alternar: () => void | Promise<void>;
}

export interface ConversaProps {
  /** O avatar com quem o Alex conversa (padrão: Zoe — original fiel). */
  avatar?: AvatarInfo;
  /** Histórico inicial (vem da fiação; formato compatível com ChatMessage). */
  historico?: ConversaMensagem[];
  /** Envia o texto e devolve a resposta real. Sem isso, nada é respondido. */
  onEnviar?: (texto: string) => Promise<string> | string;
  /** Pipeline real de voz (useZoeVoice). Sem isso, o botão explica a fiação. */
  voz?: ControladorVoz;
  /** Abrir a tela de voz dedicada. */
  onAbrirVoz?: () => void;
  providerLabel?: string;
}

const ZOE_PADRAO: AvatarInfo = {
  id: 'zoe',
  nome: 'Zoe',
  papel: 'Sua conselheira',
  imagemUrl: avatarOriginal('zoe'),
};

const SUGESTOES = ['Como está a equipe?', 'O que ficou pronto?', 'Vamos melhorar o app'];

function RetratoZoe({ avatar, className }: { avatar: AvatarInfo; className: string }) {
  if (avatar.imagemUrl) {
    return (
      <span className={className}>
        <img src={avatar.imagemUrl} alt={`${avatar.nome}, seu avatar`} />
      </span>
    );
  }
  return (
    <span className={`${className} avatar-initial`} aria-label={avatar.nome}>
      {avatar.nome.charAt(0)}
    </span>
  );
}

/** Rótulo honesto do estado real da voz. */
function rotuloVoz(voz: ControladorVoz | undefined, nome: string): string {
  if (!voz) return 'A voz está indisponível.';
  switch (voz.estado) {
    case 'starting':
      return 'Ligando o microfone…';
    case 'listening':
      return 'Ouvindo — pode falar.';
    case 'waiting':
      return `${nome} está pensando…`;
    case 'controlling':
      return 'Fazendo no seu computador…';
    case 'speaking':
      return `${nome} está falando…`;
    case 'error':
      return voz.erro || 'Algo não saiu como esperado — toque para tentar de novo.';
    case 'off':
    default:
      return `Toque e fale com ${nome}. Você fala, o piloto responde falando.`;
  }
}

export function Conversa({ avatar = ZOE_PADRAO, historico = [], onEnviar, voz, onAbrirVoz, providerLabel = 'Muse' }: ConversaProps) {
  const toast = useToast();
  const [mensagens, setMensagens] = useState<ConversaMensagem[]>(historico);
  const [texto, setTexto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erroEnvio, setErroEnvio] = useState('');
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [mensagens.length, enviando]);

  async function enviar(raw: string) {
    const conteudo = raw.trim();
    if (!conteudo || enviando) return;
    if (!onEnviar) { setErroEnvio('A conversa está indisponível. Abra sua conta para continuar.'); return; }
    const msg: ConversaMensagem = { id: crypto.randomUUID(), role: 'user', content: conteudo, timestamp: Date.now(), status: 'pending' };
    setMensagens((atual) => [...atual, msg]);
    setTexto('');
    setErroEnvio('');
    setEnviando(true);
    try {
      const resposta = await onEnviar(conteudo);
      setMensagens((atual) => [...atual.map(item => item.id === msg.id ? { ...item, status: 'sent' as const } : item), { role: 'assistant', content: resposta, timestamp: Date.now() }]);
    } catch (cause) {
      setMensagens(atual => atual.map(item => item.id === msg.id ? { ...item, status: 'unknown' } : item));
      setTexto(conteudo);
      setErroEnvio(cause instanceof Error ? cause.message : 'Não consegui confirmar a resposta. Confira sua conta antes de reenviar.');
    } finally {
      setEnviando(false);
    }
  }

  function apertarVoz() {
    if (!voz) {
      toast('A voz está indisponível.');
      return;
    }
    void voz.alternar();
  }

  const estadoVoz = voz ? mapearEstadoVoz(voz.estado) : 'ready';
  const vozAtiva = estadoVoz === 'listening' || estadoVoz === 'thinking' || estadoVoz === 'doing';

  return (
    <section className="zoe-layout" aria-label={`Conversa com ${avatar.nome}`}>
      <section className="zoe-chat">
        <header className="chat-head conversa-head">
          <RetratoZoe avatar={avatar} className="zoe-avatar" />
          <div>
            <strong>{avatar.nome}</strong>
            <small>
              {avatar.papel} · Converse por texto ou voz
            </small>
          </div>
          {onAbrirVoz ? (
            <button type="button" className="icon-button chat-voice" onClick={onAbrirVoz} aria-label="Abrir modo voz">
              <Mic size={18} aria-hidden="true" />
            </button>
          ) : null}
        </header>

        {/* Herói de voz: a ZOE com o botão de modo voz em destaque — o elemento
            mais chamativo da tela. Estados sempre reais, nunca simulados. */}
        <div className="conversa-voz-hero" data-state={estadoVoz}>
          <div className="voz-hero-avatar">
            <RetratoZoe avatar={avatar} className="voz-hero-retrato" />
            <button
              type="button"
              className="voz-hero-botao"
              onClick={apertarVoz}
              aria-label={vozAtiva ? 'Encerrar a conversa por voz' : `Falar com ${avatar.nome} por voz`}
              aria-pressed={vozAtiva}
            >
              {vozAtiva ? <MicOff size={34} aria-hidden="true" /> : <Mic size={34} aria-hidden="true" />}
            </button>
          </div>
          <div className="voz-hero-legenda" role="status" aria-live="polite">
            <strong>{rotuloVoz(voz, avatar.nome)}</strong>
            {voz?.motor ? <span>Voz: {voz.motor === 'kore' ? 'Kore' : 'OmniVoice (reserva)'}</span> : null}
          </div>
        </div>

        <div className="chat-messages" aria-live="polite">
          <div className="welcome-stamp">
            <ShieldCheck size={14} aria-hidden="true" />
            Você no comando
          </div>

          {mensagens.length === 0 ? (
            <div className="chat-welcome conversa-boasvindas">
              <h2>
                Oi, Alex.
                <br />O que vamos fazer hoje?
              </h2>
              <p>
                Uma conversa para pensar. Uma equipe para fazer. A {avatar.nome} reúne o contexto e a TROPA dev. executa as
                ações no seu computador.
              </p>
              <div className="suggestions">
                {SUGESTOES.map((s) => (
                  <button key={s} type="button" onClick={() => enviar(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div>
              {mensagens.map((m, i) =>
                m.role === 'user' ? (
                  <div className="user-bubble" key={m.id ?? i}>
                    {m.content}
                    {m.status && m.status !== 'sent' && <small style={{ display: 'block', opacity: .8 }}>{m.status === 'pending' ? 'Aguardando resposta…' : 'Resposta não confirmada'}</small>}
                  </div>
                ) : (
                  <div className="demo-response" key={m.id ?? i}>
                    <span>{m.content}</span>
                  </div>
                ),
              )}
              {enviando ? (
                <div className="demo-response digitando" aria-label="Respondendo">
                  <span className="typing-dots" aria-hidden="true">
                    •••
                  </span>
                </div>
              ) : null}
              <div ref={fimRef} />
            </div>
          )}
        </div>

        <form
          className="chat-input-wrap"
          onSubmit={(e) => {
            e.preventDefault();
            void enviar(texto);
          }}
        >
          <div className="chat-input">
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              aria-label={`Mensagem para ${avatar.nome}`}
              placeholder={`Converse com ${avatar.nome}…`}
              autoComplete="off"
              maxLength={1500}
            />
            <button
              type="button"
              className="icon-button"
              onClick={apertarVoz}
              aria-label={vozAtiva ? 'Encerrar a conversa por voz' : 'Falar em vez de digitar'}
            >
              {vozAtiva ? <MicOff size={18} aria-hidden="true" /> : <Mic size={18} aria-hidden="true" />}
            </button>
            <button type="submit" className="icon-button" aria-label="Enviar mensagem" disabled={enviando}>
              <Send size={18} aria-hidden="true" />
            </button>
          </div>
          <p className="chat-footnote">
            {onEnviar
              ? `Suas mensagens vão para a sua conversa no ${providerLabel}.`
              : 'A conversa está indisponível.'}
          </p>
          {erroEnvio && <p role="alert" className="chat-footnote">{erroEnvio}</p>}
        </form>
      </section>

      <aside className="zoe-command">
        <span className="command-label">{providerLabel.toUpperCase()} + TROPA dev.</span>
        <h3>Pensa e faz.</h3>
        <p>
          O piloto conduz a conversa. O motor conecta voz, visão, memória e ação no computador — com a segurança
          sempre ligada.
        </p>
        <div className="command-block">
          <MessageCircle size={20} aria-hidden="true" />
          <strong>Uma conversa, uma equipe</strong>
          <span>A {avatar.nome} entende o que você quer; a equipe executa no PC.</span>
        </div>
      </aside>
    </section>
  );
}
