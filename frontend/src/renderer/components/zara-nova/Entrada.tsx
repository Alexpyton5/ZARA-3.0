/** Entrada: conta real do piloto e perfil visual escolhido pelo usuario. */

import { useState } from 'react';
import { Sparkles, KeyRound, Check } from 'lucide-react';
import type { AvatarInfo } from './types';
import { getPilotAvatars } from '../../lib/pilotAvatars';
import type { PilotProvider } from '../../lib/pilotConversation';

/** Avatares da equipe que podem ser a presença com quem o Alex conversa.
 *  Imagens = originais fiéis em alta (avatares.ts). VIVA: sem asset — inicial. */
type Provedor = 'muse' | 'openai';

export interface EntradaProps {
  /** Chamado quando o Alex escolhe o avatar (a frente TEMA troca o tema do app). */
  onEscolherAvatar?: (avatar: AvatarInfo) => void;
  /** Chamado quando ele conclui a entrada e quer ir para o Início. */
  onConcluir: (avatar: AvatarInfo) => void;
  onConectar: (provider: PilotProvider) => void;
  provedor: PilotProvider;
  conectado: boolean;
}

export function Entrada({ onConcluir, onConectar, provedor, conectado }: EntradaProps) {
  const avatares = getPilotAvatars(provedor);
  const [avatarId, setAvatarId] = useState('');
  const avatar = avatares.find(item => item.id === avatarId) || avatares[0];

  function escolher(novo: AvatarInfo) {
    setAvatarId(novo.id);
  }

  function conectar(provedor: Provedor) {
    onConectar(provedor);
  }

  return (
    <section className="entrada-view" aria-label="Primeiros passos">
      <div className="entrada-hero">
        <p className="eyebrow">BEM-VINDO À TROPA dev.</p>
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
            className={`provider-row${provedor === 'muse' && conectado ? ' connected' : ''}`}
            onClick={() => conectar('muse')}
            aria-pressed={provedor === 'muse' && conectado}
          >
            <span className="provider-icon" aria-hidden="true">
              <Sparkles size={20} />
            </span>
            <div className="provider-copy">
              <strong>Conectar Muse</strong>
              <span>O cérebro que pensa com você.</span>
            </div>
            {provedor === 'muse' && conectado ? <Check size={18} aria-label="Conversa disponível" /> : null}
          </button>

          <button
            type="button"
            className={`provider-row${provedor === 'openai' && conectado ? ' connected' : ''}`}
            onClick={() => conectar('openai')}
            aria-pressed={provedor === 'openai' && conectado}
          >
            <span className="provider-icon" aria-hidden="true">
              <KeyRound size={20} />
            </span>
            <div className="provider-copy">
              <strong>Conectar OpenAI</strong>
              <span>Alternativa para conversar e criar.</span>
            </div>
            {provedor === 'openai' && conectado ? <Check size={18} aria-label="Conversa disponível" /> : null}
          </button>

          <p className="entrada-note">Seu login fica salvo. Você pode abrir sua conta novamente dentro do app.</p>
        </div>

        <div className="entrada-card">
          <div className="card-heading">
            <h2>Escolher o avatar</h2>
            <span className="subtle-badge">Vale para o app todo</span>
          </div>
          <div className="avatar-picker" role="radiogroup" aria-label="Escolha do avatar">
            {avatares.map((a) => (
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
            {avatar.nome} será o rosto da sua experiência. {provedor === 'openai' ? 'A conversa usa sua conta ChatGPT; o catálogo nativo de Dots ainda não está conectado.' : 'A conversa segue a sessão Muse que você abrir na sua conta.'}
          </p>
        </div>
      </div>

      <div className="entrada-actions">
        <button type="button" className="primary-button" onClick={() => onConcluir(avatar)}>
          Começar com {avatar.nome}
        </button>
      </div>
    </section>
  );
}
