/** Avatares originais fiéis em alta — NUNCA redesenhar, NUNCA inventar traço/cor/roupa.
 *
 *  Achado 2026-09-30 (adendo do Alex): os hotlinks .png do molde caíram
 *  (o site agora devolve a página HTML nesses caminhos). Os originais fiéis
 *  estão no ar como .webp — conferidos um a um, são os avatares originais
 *  em alta (a zoe-reference é o mascote 4UP de trança loira, cropped preto +
 *  short verde 4UP). A VIVA não tem asset (era "pendente" no molde) —
 *  quem usa VIVA cai no fallback de inicial.
 *
 *  Se o site sair do ar, trocar por cópias locais dos mesmos arquivos. */

import zoeLimpa from '../../assets/zoe-limpa.png';

const BASE = 'https://zara-ui-lab.zoeeproject.chatgpt.site/assets';

export const AVATAR_ORIGINAL: Record<string, string> = {
  zoe: zoeLimpa, // retrato limpo local (o .webp do molde vinha com texto embutido)
  lyra: `${BASE}/lyra.webp`,
  levi: `${BASE}/levi.webp`,
  azul: `${BASE}/azul.webp`,
  kai: `${BASE}/kai.webp`,
  noa: `${BASE}/noa.webp`,
  nix: `${BASE}/nix.webp`,
  // viva: sem asset original (pendente no molde) — fallback de inicial.
};

/** URL do avatar original fiel, ou undefined quando não existe. */
export function avatarOriginal(id: string): string | undefined {
  return AVATAR_ORIGINAL[id];
}
