import alfred from '../assets/alfred-reference.png';
import { avatarOriginal } from '../components/zara-nova/avatares';
import type { AvatarInfo } from '../components/zara-nova/types';
import type { PilotProvider } from './pilotConversation';

// Alfred is cropped from Alex's screenshot; only the light background was removed.
// This local visual profile is not a catalog retrieved from an OpenAI account.
export function getPilotAvatars(provider: PilotProvider): AvatarInfo[] {
  if (provider === 'openai') return [{ id: 'alfred', nome: 'Alfred', papel: 'Seu copiloto', imagemUrl: alfred }];
  return [
    ['zoe', 'Zoe', 'Sua conselheira'], ['lyra', 'LYRA', 'Voz da TROPA dev.'],
    ['levi', 'LEVI', 'Use Computer'], ['azul', 'AZUL', 'Integrações'],
    ['kai', 'KAI', 'Build & Lançamento'], ['noa', 'NOA', 'Cérebro & Autopilot'],
    ['nix', 'NIX', 'Nome & Produto'], ['dex', 'DEX', 'Engenharia'],
    ['atlas', 'ATLAS', 'Arquitetura'], ['mia', 'MIA', 'Marketing'],
  ].map(([id, nome, papel]) => ({ id, nome, papel, imagemUrl: avatarOriginal(id) }));
}

export function pilotAvatar(id: string, provider: PilotProvider): AvatarInfo | null {
  return getPilotAvatars(provider).find(avatar => avatar.id === id) || null;
}
