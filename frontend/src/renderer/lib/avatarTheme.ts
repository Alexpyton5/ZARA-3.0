/**
 * Temas e metadados dos avatares da interface nova.
 * Família Muse: zara-claro / zara-escuro. Alfred: dots, conforme ordem de Alex.
 * Este mapa define aparência; a disponibilidade dos provedores é tratada fora daqui.
 * Retratos locais em avatares.ts. O ZIP foi usado como referência visual e de assets.
 */

import type { AvatarId, AvatarInfo, ThemeId } from '../components/zara-nova/types';
import { avatarOriginal } from '../components/zara-nova/avatares';

/** Opção de tema exibida nos seletores da interface (rótulos em pt-BR). */
export interface ThemeOption {
  id: ThemeId;
  rotulo: string;
  descricao: string;
}

/** Temas já existentes na folha de estilos, com rótulos em pt-BR. */
export const AVAILABLE_THEMES: ThemeOption[] = [
  {
    id: 'zara-claro',
    rotulo: 'Claro acolhedor',
    descricao:
      'Fundo claro e quente para a família Muse.',
  },
  {
    id: 'zara-escuro',
    rotulo: 'Verde noturno',
    descricao: 'O verde-escuro original do molde: foco total para acompanhar o trabalho.',
  },
  {
    id: 'dots',
    rotulo: 'Alfred dourado',
    descricao: 'Grafite e dourado; identidade visual da tripulação OpenAI.',
  },
];

/** Qual tema cada avatar veste. */
export const AVATAR_THEMES: Record<AvatarId, ThemeId> = {
  zoe: 'zara-claro',
  lyra: 'zara-claro',
  viva: 'zara-claro',
  kai: 'zara-escuro',
  noa: 'zara-escuro',
  azul: 'zara-escuro',
  levi: 'zara-claro',
  nix: 'zara-claro',
  alfred: 'dots',
};

/** Avatar padrão quando não há escolha salva. */
export const DEFAULT_AVATAR_ID: AvatarId = 'zoe';

/** Tema padrão quando não há escolha salva (o tema de referência). */
export const DEFAULT_THEME_ID: ThemeId = 'zara-claro';

/** Nome e papel oficiais de cada avatar da equipe (ponte com a FRENTE FIAÇÃO).
 *  Valores vindos da tela Entrada da FRENTE TELAS CORE — nada inventado. */
export interface AvatarResumo {
  nome: string;
  papel: string;
}

export const AVATAR_INFO: Record<AvatarId, AvatarResumo> = {
  zoe: { nome: 'Zoe', papel: 'Sua conselheira' },
  lyra: { nome: 'LYRA', papel: 'Voz da ZARA' },
  levi: { nome: 'LEVI', papel: 'Use Computer' },
  azul: { nome: 'AZUL', papel: 'Integrações' },
  kai: { nome: 'KAI', papel: 'Build & Lançamento' },
  noa: { nome: 'NOA', papel: 'Cérebro & Autopilot' },
  nix: { nome: 'NIX', papel: 'Nome & Produto' },
  viva: { nome: 'VIVA', papel: 'Mídias Sociais' },
  alfred: { nome: 'Alfred', papel: 'Seu copiloto' },
};

/** Monta o AvatarInfo de um id (ponte com o contrato que a FRENTE FIAÇÃO espera). */
export function avatarInfoPara(id: AvatarId): AvatarInfo {
  const info = AVATAR_INFO[id];
  return info
    ? { id, nome: info.nome, papel: info.papel, imagemUrl: avatarOriginal(id) }
    : { id, nome: id, papel: '', imagemUrl: avatarOriginal(id) };
}

/** Devolve o tema do avatar; avatar desconhecido cai no tema de referência. */
export function themeForAvatar(avatarId: AvatarId): ThemeId {
  return AVATAR_THEMES[avatarId] ?? DEFAULT_THEME_ID;
}

/** Confere se um valor vindo de fora (ex.: localStorage) é um tema válido. */
export function isKnownTheme(value: unknown): value is ThemeId {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    AVAILABLE_THEMES.some((option) => option.id === value)
  );
}

/** Asset fiel de cada avatar (ordem do Alex: nunca aproximado, nunca inventado). */
export interface AvatarAsset {
  /** Nome do arquivo do asset fiel. */
  arquivo: string;
  /** Caminho da referência original dentro do ZIP fornecido. */
  origem: string;
  /** O que o asset mostra — tem que bater com o original na conferência visual. */
  descricao: string;
}

/** Registro de qual asset cada avatar usa e de onde veio. */
export const AVATAR_ASSETS: Record<string, AvatarAsset> = {
  zoe: {
    arquivo: 'zoe-limpa.png',
    origem: 'frontend/src/renderer/assets/zoe-limpa.png; mesma personagem da referência zoe-reference.webp do ZIP',
    descricao:
      'Mascote 4UP de trança loira; cropped preto 4UP; short verde 4UP; tatuagens; relógio branco; bola amarela e preta.',
  },
  lyra: {
    arquivo: 'lyra.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem de pelúcia, cabelo castanho comprido, headset e camiseta clara 4UP.',
  },
  levi: {
    arquivo: 'levi.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem de pelúcia com óculos, capuz creme e camiseta preta 4UP.',
  },
  kai: {
    arquivo: 'kai.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem KAI original no arquivo kai.webp do ZIP fornecido.',
  },
  noa: {
    arquivo: 'noa.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem NOA original no arquivo noa.webp do ZIP fornecido.',
  },
  azul: {
    arquivo: 'azul.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem AZUL original no arquivo azul.webp do ZIP fornecido.',
  },
  nix: {
    arquivo: 'nix.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem NIX original no arquivo nix.webp do ZIP fornecido.',
  },
  dex: {
    arquivo: 'dex.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao: 'Personagem DEX original no arquivo dex.webp do ZIP fornecido.',
  },
  atlas: {
    arquivo: 'atlas.webp',
    origem: '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/',
    descricao:
      'Personagem ATLAS original no arquivo atlas.webp do ZIP fornecido.',
  },
  mia: {
    arquivo: 'mia.webp',
    origem:
      '.zara-dev/references/prototipo-gpt-20260930/ZARA_Prototipo/dist/assets/mia.webp',
    descricao: 'Personagem MIA original no arquivo mia.webp do ZIP fornecido.',
  },
  viva: {
    arquivo: '(pendente)',
    origem: 'Nenhum arquivo viva encontrado em dist/assets do ZIP fornecido.',
    descricao: 'Avatar pendente: nada inventado até a referência oficial chegar.',
  },
};
