/** Tela Conversa: o avatar no centro, conversa em texto + voz.
 *  REGRA DE LINGUAGEM: quem conversa é o avatar (a presença de confiança).
 *  A ZARA é o motor que executa — nunca personagem, nunca em 1ª pessoa.
 *
 *  VOZ EM DESTAQUE (adendo do Alex): o botão de modo voz é o elemento mais
 *  chamativo da tela, com a ZOE (avatar do Muse dele — mascote de trança
 *  loira, cropped preto + short verde 4UP, original fiel) ao lado/atrás.
 *  A conversa por voz é NATURAL e em tempo real: ele fala, ela responde
 *  FALANDO — via o pipeline real `useZoeVoice` (não é só ler texto em voz alta).
 *
 *  FIAÇÃO (outra frente):
 *  - Histórico inicial: normalizar a resposta do IPC com
 *    `normalizeHistoryResponse(resposta)` (pc-source/renderer/lib/chatHistory.ts).
 *    // TODO(CODEX): carregar o histórico real via IPC e passar em `historico`.
 *  - Texto: `submitToMuse(webview, texto)` + `readMuseReply(webview, sub)`
 *    (pc-source/renderer/lib/museConversation.ts) precisam do webview da conversa
 *    com a zoe.
 *    // TODO(CODEX): ligar onEnviar ao webview (submitToMuse/readMuseReply).
 *  - VOZ: passar em `voz` o controlador ligado ao `useZoeVoice(webviewRef, pageReady)`
 *    (pc-source/renderer/lib/useZoeVoice.ts): { estado, erro, motor, alternar }.
 *    // TODO(CODEX): instanciar useZoeVoice na montagem da tela e fiar `voz`.
 *    // TODO(CODEX): GAP REAL — Manual §8.2: 'zoe-voice-speak' não tem handler no
 *    backend; o TTS por esse caminho não chega. O áudio real chega pelo evento
 *    'voice-output-audio' (PCM da Kore). Registrar o handler ou remover a chamada
 *    morta — documentar a decisão. Ver skill verificacao-voz (os 4 passos).
 *  Sem fiação, NADA é fingido: nenhum estado de voz é simulado, nenhuma
 *  resposta é inventada — o rodapé e o botão explicam honestamente. */

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
function rotuloVoz(voz: ControladorVoz | undefined): string {
  if (!voz) return 'A voz conecta na etapa de fiação.';
  switch (voz.estado) {
    case 'starting':
      return 'Ligando o microfone…';
    case 'listening':
      return 'Ouvindo — pode falar.';
    case 'waiting':
      return 'A Zoe está pensando…';
    case 'controlling':
      return 'Fazendo no seu computador…';
    case 'speaking':
      return 'A Zoe está falando…';
    case 'error':
      return voz.erro || 'Algo não saiu como esperado — toque para tentar de novo.';
    case 'off':
    default:
      return 'Toque e fale com a Zoe. Você fala, ela responde falando.';
  }
}

export function Conversa({ avatar = ZOE_PADRAO, historico = [], onEnviar, voz, onAbrirVoz }: ConversaProps) {
  const toast = useToast();
  const [mensagens, setMensagens] = useState<ConversaMensagem[]>(historico);
  const [texto, setTexto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [mensagens.length, enviando]);

  async function enviar(raw: string) {
    const conteudo = raw.trim();
    if (!conteudo || enviando) return;
    const msg: ConversaMensagem = { role: 'user', content: conteudo, timestamp: Date.now() };
    setMensagens((atual) => [...atual, msg]);
    setTexto('');

    if (!onEnviar) {
      // Sem fiação real, não inventamos resposta.
      toast('Mensagem registrada. A conversa de verdade conecta na etapa de fiação.');
      return;
    }

    setEnviando(true);
    try {
      const resposta = await onEnviar(conteudo);
      setMensagens((atual) => [...atual, { role: 'assistant', content: resposta, timestamp: Date.now() }]);
    } catch {
      toast('Não consegui enviar agora. Tente de novo em instantes.');
    } finally {
      setEnviando(false);
    }
  }

  function apertarVoz() {
    if (!voz) {
      toast('A voz de verdade conecta na etapa de fiação.');
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
              aria-label={vozAtiva ? 'Encerrar a conversa por voz' : 'Falar com a Zoe por voz'}
              aria-pressed={vozAtiva}
            >
              {vozAtiva ? <MicOff size={34} aria-hidden="true" /> : <Mic size={34} aria-hidden="true" />}
            </button>
          </div>
          <div className="voz-hero-legenda" role="status" aria-live="polite">
            <strong>{rotuloVoz(voz)}</strong>
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
                Uma conversa para pensar. Uma equipe para fazer. A {avatar.nome} reúne o contexto e a ZARA executa as
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
              ? 'Suas mensagens vão para a conversa com a zoe.'
              : 'A conversa de verdade conecta na etapa de fiação — nada aqui é respondido por enquanto.'}
          </p>
        </form>
      </section>

      <aside className="zoe-command">
        <span className="command-label">MUSE + ZARA</span>
        <h3>Pensa e faz.</h3>
        <p>
          O Muse é o cérebro. O app é o corpo: voz, visão, memória e ação no computador — com a trava de segurança
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
