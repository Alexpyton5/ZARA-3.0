/**
 * avatarTheme.ts — o motor de temas: qual avatar veste qual tema.
 *
 * REGRA DO Alex: trocar o avatar ativo troca o tema do app INTEIRO, sem reload,
 * e a escolha persiste (ver ThemeProvider em components/zara-nova/theme/).
 *
 * ---------------------------------------------------------------------------
 * DECISÃO DE DESIGN (UI designer, 2026-09-30)
 * ---------------------------------------------------------------------------
 * Os 3 temas vêm do molde aprovado (zara-nova.css):
 *   zara-claro  — claro, quente e respirável; a REFERÊNCIA OFICIAL de UI
 *                 (a versão vencedora do duelo de protótipos, no estilo do Muse AI).
 *   zara-escuro — o verde-escuro original do molde; o "modo trabalho".
 *   dots        — dark cinematográfico com gradiente azul→roxo→rosa→amarelo;
 *                 a demonstração viva do motor de temas (1 clique muda tudo).
 *
 * O mapa abaixo segue o papel de cada avatar na equipe:
 *   zoe, lyra, viva -> zara-claro. A zoe é a presença principal — a pessoa com
 *     quem o usuário conversa e em quem confia — então ela veste o tema de
 *     referência. A lyra (voz) e a viva (mídias sociais) pedem acolhimento,
 *     então ficam no claro também.
 *   kai, noa, azul -> zara-escuro. São os avatares de execução (build, cérebro
 *     e integrações): o verde-escuro dá o clima de centro de comando, foco total.
 *   levi, nix -> dots. O levi É o personagem de óculos do molde (identificado
 *     visualmente: óculos no rosto, touca creme, camiseta preta 4UP) — o tema
 *     mais expressivo combina com ele. A nix (Nome & Produto) trabalha criação,
 *     então o dark cinematográfico veste bem o trabalho criativo.
 *
 * Avatar desconhecido cai no zara-claro (o tema de referência é o padrão seguro).
 *
 * ---------------------------------------------------------------------------
 * REGISTRO DE ASSETS — ordem do Alex (2026-09-30): avatares SEMPRE fiéis aos
 * originais, em ótima qualidade. Proibido redesenhar aproximado; nunca inventar
 * traço, cor ou roupa. Onde a interface referenciar um avatar, usar o asset
 * fiel abaixo. Se a resolução do molde for baixa, reconstruir a partir do
 * original fiel — nunca inventar.
 * ---------------------------------------------------------------------------
 *   zoe  -> media-generation-mascote-4up-tranca-0-2b5600e2-5fd4-4e8e-86a7-92a97264113a.webp
 *           origem: ~/workspace/4up/mascote/ (original fiel gerado em 2026-09-28)
 *   lyra -> lyra.png   | origem: ~/workspace/ts-spaces/zara-ui-lab/assets/
 *   levi -> levi.png   |   (cópias locais fiéis dos PNGs do molde,
 *   kai  -> kai.png    |    mesmos arquivos servidos em
 *   noa  -> noa.png    |    https://zara-ui-lab.zoeeproject.chatgpt.site/assets/<nome>.png)
 *   azul -> azul.png   |
 *   nix  -> nix.png    |
 *   dex  -> dex.png    |   (salas adicionais do molde)
 *   atlas-> atlas.png  |
 *   mia  -> mia.png    | origem: só no hotlink do molde (sem cópia local ainda)
 *   viva -> (pendente) | sem asset no molde — a referência visual ainda precisa
 *                        ser fornecida; nada inventado até lá.
 *
 * Descrição visual de cada um (para conferência — tem que bater com o original):
 *   zoe:   mascote 4UP de trança loira; cropped preto 4UP; short verde 4UP;
 *          tatuagens nos braços; relógio branco; bola amarela e preta.
 *   lyra:  hamster, cabelo castanho comprido; headset com microfone; camiseta clara 4UP.
 *   levi:  hamster de óculos (o personagem de óculos); touca creme; camiseta preta 4UP.
 *   kai:   hamster, boné bege 4UP; camiseta bege 4UP; cinto de ferramentas; short jeans.
 *   noa:   hamster, moletom cinza com capuz.
 *   azul:  hamster de pelo escuro; camiseta verde 4UP; headset com microfone.
 *   nix:   hamster, tranças castanhas; camiseta azul 4UP.
 *   dex:   hamster de pelo escuro, óculos na testa; camiseta preta 4UP.
 *   atlas: hamster, cabelo grisalho, óculos; camisa polo azul-petróleo; segura projeto.
 */

import type { AvatarId, AvatarInfo, ThemeId } from '../components/zara-nova/types';

/** Opção de tema exibida nos seletores da interface (rótulos em pt-BR). */
export interface ThemeOption {
  id: ThemeId;
  rotulo: string;
  descricao: string;
}

/** Os 3 temas disponíveis, com rótulos em pt-BR simples. */
export const AVAILABLE_THEMES: ThemeOption[] = [
  {
    id: 'zara-claro',
    rotulo: 'Claro acolhedor',
    descricao:
      'A referência oficial: fundo claro, quente e respirável, no estilo da interface do Muse AI.',
  },
  {
    id: 'zara-escuro',
    rotulo: 'Verde noturno',
    descricao: 'O verde-escuro original do molde: foco total para acompanhar o trabalho.',
  },
  {
    id: 'dots',
    rotulo: 'Dots cinematográfico',
    descricao:
      'Dark com gradiente azul, roxo, rosa e amarelo. A demonstração viva do motor de temas.',
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
  levi: 'dots',
  nix: 'dots',
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
};

/** Monta o AvatarInfo de um id (ponte com o contrato que a FRENTE FIAÇÃO espera). */
export function avatarInfoPara(id: AvatarId): AvatarInfo {
  const info = AVATAR_INFO[id];
  return info
    ? { id, nome: info.nome, papel: info.papel }
    : { id, nome: id, papel: '' };
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
  /** De onde veio o asset (caminho local ou URL do molde). */
  origem: string;
  /** O que o asset mostra — tem que bater com o original na conferência visual. */
  descricao: string;
}

/** Registro de qual asset cada avatar usa e de onde veio. */
export const AVATAR_ASSETS: Record<string, AvatarAsset> = {
  zoe: {
    arquivo: 'media-generation-mascote-4up-tranca-0-2b5600e2-5fd4-4e8e-86a7-92a97264113a.webp',
    origem: '~/workspace/4up/mascote/ (original fiel gerado em 2026-09-28)',
    descricao:
      'Mascote 4UP de trança loira; cropped preto 4UP; short verde 4UP; tatuagens; relógio branco; bola amarela e preta.',
  },
  lyra: {
    arquivo: 'lyra.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster, cabelo castanho comprido; headset com microfone; camiseta clara 4UP.',
  },
  levi: {
    arquivo: 'levi.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster de óculos (o personagem de óculos); touca creme; camiseta preta 4UP.',
  },
  kai: {
    arquivo: 'kai.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster, boné bege 4UP; camiseta bege 4UP; cinto de ferramentas; short jeans.',
  },
  noa: {
    arquivo: 'noa.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster, moletom cinza com capuz.',
  },
  azul: {
    arquivo: 'azul.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster de pelo escuro; camiseta verde 4UP; headset com microfone.',
  },
  nix: {
    arquivo: 'nix.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster, tranças castanhas; camiseta azul 4UP.',
  },
  dex: {
    arquivo: 'dex.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao: 'Hamster de pelo escuro, óculos na testa; camiseta preta 4UP. (Sala adicional.)',
  },
  atlas: {
    arquivo: 'atlas.png',
    origem: '~/workspace/ts-spaces/zara-ui-lab/assets/ (cópia fiel do PNG do molde)',
    descricao:
      'Hamster, cabelo grisalho, óculos; camisa polo azul-petróleo; segura o projeto. (Sala adicional.)',
  },
  mia: {
    arquivo: 'mia.png',
    origem:
      'Apenas no hotlink do molde (https://zara-ui-lab.zoeeproject.chatgpt.site/assets/mia.png) — sem cópia local ainda.',
    descricao: 'Asset pendente de download local. (Sala adicional.)',
  },
  viva: {
    arquivo: '(pendente)',
    origem: 'Sem asset no molde — a referência visual ainda precisa ser fornecida.',
    descricao: 'Avatar pendente: nada inventado até a referência oficial chegar.',
  },
};
