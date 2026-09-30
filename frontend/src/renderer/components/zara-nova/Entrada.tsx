/** Tela de Entrada (onboarding): conectar a mente (Muse / OpenAI) e escolher o avatar.
 *  A interface inteira acompanha a escolha do avatar: personagens, cores, ícones e ambiente.
 *
 *  Integração real de contas: // TODO(CODEX) — os botões de conectar disparam
 *  a fiação da outra frente; aqui eles só registram a intenção localmente. */

import { useState } from 'react';
import { Sparkles, KeyRound, Check } from 'lucide-react';
import type { AvatarInfo } from './types';
import { avatarOriginal } from './avatares';
import { useToast } from './chrome/ZaraNovaShell';

/** Avatares da equipe que podem ser a presença com quem o Alex conversa.
 *  Imagens = originais fiéis em alta (avatares.ts). VIVA: sem asset — inicial. */
const AVATARES: AvatarInfo[] = [
  { id: 'zoe', nome: 'Zoe', papel: 'Sua conselheira', imagemUrl: avatarOriginal('zoe') },
  { id: 'lyra', nome: 'LYRA', papel: 'Voz da ZARA', imagemUrl: avatarOriginal('lyra') },
  { id: 'levi', nome: 'LEVI', papel: 'Use Computer', imagemUrl: avatarOriginal('levi') },
  { id: 'azul', nome: 'AZUL', papel: 'Integrações', imagemUrl: avatarOriginal('azul') },
  { id: 'kai', nome: 'KAI', papel: 'Build & Lançamento', imagemUrl: avatarOriginal('kai') },
  { id: 'noa', nome: 'NOA', papel: 'Cérebro & Autopilot', imagemUrl: avatarOriginal('noa') },
  { id: 'nix', nome: 'NIX', papel: 'Nome & Produto', imagemUrl: avatarOriginal('nix') },
  { id: 'viva', nome: 'VIVA', papel: 'Mídias Sociais' },
];

type Provedor = 'muse' | 'openai';

export interface EntradaProps {
  /** Chamado quando o Alex escolhe o avatar (a frente TEMA troca o tema do app). */
  onEscolherAvatar?: (avatar: AvatarInfo) => void;
  /** Chamado quando ele conclui a entrada e quer ir para o Início. */
  onConcluir?: () => void;
}

export function Entrada({ onEscolherAvatar, onConcluir }: EntradaProps) {
  const toast = useToast();
  const [avatar, setAvatar] = useState<AvatarInfo>(AVATARES[0]);
  const [conectados, setConectados] = useState<Set<Provedor>>(new Set());

  function escolher(novo: AvatarInfo) {
    setAvatar(novo);
    onEscolherAvatar?.(novo);
  }

  function conectar(provedor: Provedor) {
    // TODO(CODEX): abrir aqui o fluxo real de conexão da conta
    // (Muse / OpenAI) e persistir a credencial no cofre do app.
    // O clique só REGISTRA A INTENÇÃO — não conecta nada de verdade.
    setConectados((atual) => new Set(atual).add(provedor));
    toast(
      provedor === 'muse'
        ? 'Intenção registrada: conectar o Muse. A conexão de verdade chega na etapa de fiação.'
        : 'Intenção registrada: conectar a OpenAI. A conexão de verdade chega na etapa de fiação.',
    );
  }

  return (
    <section className="entrada-view" aria-label="Primeiros passos">
      <div className="entrada-hero">
        <p className="eyebrow">BEM-VINDO À ZARA</p>
        <h2>
          Uma mente para pensar.
          <br />
          Um corpo para fazer.
        </h2>
        <p>
          Conecte a inteligência que vai conversar com você e escolha o avatar
          que vai te acompanhar. O app inteiro — cores, personagens e ambiente —
          segue essa escolha.
        </p>
      </div>

      <div className="entrada-grid">
        <div className="entrada-card">
          <div className="card-heading">
            <h2>Conectar a mente</h2>
          </div>

          <button
            type="button"
            className={`provider-row${conectados.has('muse') ? ' connected' : ''}`}
            onClick={() => conectar('muse')}
            aria-pressed={conectados.has('muse')}
          >
            <span className="provider-icon" aria-hidden="true">
              <Sparkles size={20} />
            </span>
            <div className="provider-copy">
              <strong>Conectar Muse</strong>
              <span>O cérebro que pensa com você.</span>
            </div>
            {conectados.has('muse') ? <Check size={18} aria-label="Intenção registrada" /> : null}
          </button>

          <button
            type="button"
            className={`provider-row${conectados.has('openai') ? ' connected' : ''}`}
            onClick={() => conectar('openai')}
            aria-pressed={conectados.has('openai')}
          >
            <span className="provider-icon" aria-hidden="true">
              <KeyRound size={20} />
            </span>
            <div className="provider-copy">
              <strong>Conectar OpenAI</strong>
              <span>Alternativa para conversar e criar.</span>
            </div>
            {conectados.has('openai') ? <Check size={18} aria-label="Intenção registrada" /> : null}
          </button>

          <p className="entrada-note">Você pode pular e conectar depois, nas configurações.</p>
        </div>

        <div className="entrada-card">
          <div className="card-heading">
            <h2>Escolher o avatar</h2>
            <span className="subtle-badge">Vale para o app todo</span>
          </div>
          <div className="avatar-picker" role="radiogroup" aria-label="Escolha do avatar">
            {AVATARES.map((a) => (
              <button
                key={a.id}
                type="button"
                role="radio"
                aria-checked={avatar.id === a.id}
                className={`avatar-option${avatar.id === a.id ? ' active' : ''}`}
                onClick={() => escolher(a)}
              >
                {a.imagemUrl ? (
                  <img src={a.imagemUrl} alt="" loading="lazy" />
                ) : (
                  <span className="avatar-initial" aria-hidden="true">
                    {a.nome.charAt(0)}
                  </span>
                )}
                <strong>{a.nome}</strong>
                <small>{a.papel}</small>
              </button>
            ))}
          </div>
          <p className="entrada-note">
            {avatar.nome} vai ser a presença com quem você conversa — e quem você confia.
          </p>
        </div>
      </div>

      <div className="entrada-actions">
        <button type="button" className="primary-button" onClick={() => onConcluir?.()}>
          Começar com {avatar.nome}
        </button>
      </div>
    </section>
  );
}
