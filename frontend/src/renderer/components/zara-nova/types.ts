/** Tipos de domínio compartilhados da interface nova da ZARA.
 *  Contrato entre as frentes: não renomear sem avisar o coordenador. */

export type AvatarId = string; // ex.: 'zoe', 'lyra', 'levi', 'azul', 'kai', 'noa', 'nix', 'viva'

export type ThemeId = 'zara-claro' | 'zara-escuro' | 'dots' | string;

export type NavKey = 'inicio' | 'conversa' | 'voz' | 'atividade' | 'equipe' | 'lab';

export interface AvatarInfo {
  id: AvatarId;
  nome: string;
  papel: string; // ex.: 'Voz da ZARA'
  imagemUrl?: string;
}

/** Quem está cuidando do computador agora (tela Início). */
export interface CuidandoInfo {
  avatar: AvatarInfo;
  /** true = supercérebro ligado (ele está olhando); false = operando sozinha */
  supervisionado: boolean;
  desde?: string;
}

export interface TrabalhoItem {
  id: string;
  titulo: string;
  descricao: string;
  responsavel: AvatarInfo;
  estado: 'andamento' | 'entregue' | 'pausado';
  atualizadoEm: string;
}

export interface DecisaoItem {
  id: string;
  pergunta: string;
  contexto: string;
  opcoes: string[];
}

export interface AtividadeItem {
  id: string;
  titulo: string;
  descricao: string;
  responsavel: AvatarInfo;
  concluidoEm: string;
  /** Só existe se houver capacidade real de desfazer. */
  podeDesfazer?: boolean;
  entregavelUrl?: string;
}

export interface ProjetoUsuario {
  id: string;
  nome: string;
  membros: MembroEquipe[];
}

export interface MembroEquipe {
  avatar: AvatarInfo;
  status: 'trabalhando' | 'pausado' | 'disponivel';
  tarefaAtual?: string;
}

export type VoiceState = 'ready' | 'listening' | 'thinking' | 'doing' | 'error';
