/** Originais do ZIP fornecido por Alex, preservados sem alteração.
 * Zoe mantém a cópia limpa já existente do mesmo desenho; VIVA não tem referência.
 * Este registro contém imagens, não um catálogo de provedores ou capacidades.
 */
import atlas from '../../assets/prototipo/atlas.webp';
import azul from '../../assets/prototipo/azul.webp';
import dex from '../../assets/prototipo/dex.webp';
import kai from '../../assets/prototipo/kai.webp';
import levi from '../../assets/prototipo/levi.webp';
import lyra from '../../assets/prototipo/lyra.webp';
import mia from '../../assets/prototipo/mia.webp';
import nix from '../../assets/prototipo/nix.webp';
import noa from '../../assets/prototipo/noa.webp';
import zoe from '../../assets/zoe-avatar.svg';

export const AVATAR_ORIGINAL: Readonly<Record<string, string>> = {
  zoe, lyra, levi, azul, kai, noa, nix, dex, atlas, mia,
};

/** Imagem local fiel, ou undefined quando a referência não foi fornecida. */
export function avatarOriginal(id: string): string | undefined {
  const key = id.trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(AVATAR_ORIGINAL, key)
    ? AVATAR_ORIGINAL[key]
    : undefined;
}
