export interface PeleAparencia {
  id: string;
  nome: string;
  fundo: string;
  destaque: string;
  segundoFio: string;
}

export const PELES_APARENCIA = [
  { id: 'militar', nome: 'Militar', fundo: '#0B0F0B', destaque: '#8FC17F', segundoFio: '#C0392B' },
  { id: 'berbere', nome: 'Berbere', fundo: '#0E2415', destaque: '#E8C15A', segundoFio: '#C0392B' },
  { id: 'oliva', nome: 'Oliva', fundo: '#14170E', destaque: '#C9A227', segundoFio: '#8A5A2B' },
  { id: 'terracota', nome: 'Terracota', fundo: '#17110D', destaque: '#C4643A', segundoFio: '#D9A441' },
  { id: 'marrakesh', nome: 'Marrakesh', fundo: '#1A120C', destaque: '#D98E36', segundoFio: '#2E6B5E' },
  { id: 'grafite', nome: 'Grafite', fundo: '#15130F', destaque: '#E39A2B', segundoFio: '#7A6A55' },
  { id: 'aco', nome: 'Aço', fundo: '#0D1117', destaque: '#7FB3FF', segundoFio: '#4A6076' },
  { id: 'cobre', nome: 'Cobre', fundo: '#0C0C0C', destaque: '#C87941', segundoFio: '#6E5240' },
  { id: 'papel', nome: 'Papel', fundo: '#FAFAF6', destaque: '#1B4D3E', segundoFio: '#B4552E' },
  { id: 'linho', nome: 'Linho', fundo: '#EFE9DC', destaque: '#8C7A57', segundoFio: '#B39B72' },
  { id: 'egeu', nome: 'Egeu', fundo: '#F4F1E8', destaque: '#1F4E6B', segundoFio: '#C4643A' },
  { id: 'osso', nome: 'Osso', fundo: '#F3EFE4', destaque: '#5A6B36', segundoFio: '#A6784B' },
  { id: 'gelo', nome: 'Gelo', fundo: '#EEF1F2', destaque: '#2F6B60', segundoFio: '#9AAFA9' },
] as const satisfies readonly PeleAparencia[];

export const PADROES_APARENCIA = [
  // Os 17 do kit de testes, na mesma ordem e com os mesmos desenhos —
  // gerados junto com o CSS por scratchpad/gerar_padroes.py para as duas
  // listas nunca divergirem. Ver padroes.css.
  { id: 'sem', nome: 'Sem' },
  { id: 'zellige', nome: 'Zellige' },
  { id: 'khatim', nome: 'Khatim' },
  { id: 'girih', nome: 'Girih' },
  { id: 'mashrabiya', nome: 'Mashrabiya' },
  { id: 'zulaij', nome: 'Zulaij' },
  { id: 'mocarabe', nome: 'Mocárabe' },
  { id: 'meandro', nome: 'Meandro' },
  { id: 'onda-grega', nome: 'Onda grega' },
  { id: 'palmeta', nome: 'Palmeta' },
  { id: 'ovos-dardos', nome: 'Ovos e dardos' },
  { id: 'losango', nome: 'Losango' },
  { id: 'chevron', nome: 'Chevron' },
  { id: 'tranca', nome: 'Trança' },
  { id: 'olho', nome: 'Olho' },
  { id: 'grade-fina', nome: 'Grade fina' },
  { id: 'pontos', nome: 'Pontos' },
  { id: 'fio-diagonal', nome: 'Fio diagonal' },
] as const;

export const POSICOES_PADRAO = [
  { id: 'faixa-lateral', nome: 'Faixa lateral' },
  { id: 'rodape', nome: 'Rodapé' },
  { id: 'fundo-inteiro', nome: 'Fundo inteiro' },
  { id: 'sem', nome: 'Sem' },
] as const;

export const FORCAS_PADRAO = [
  { id: 'sutil', nome: 'Sutil' },
  { id: 'media', nome: 'Média' },
  { id: 'forte', nome: 'Forte' },
] as const;

export type PadraoAparencia = typeof PADROES_APARENCIA[number]['id'];
export type PosicaoPadrao = typeof POSICOES_PADRAO[number]['id'];
export type ForcaPadrao = typeof FORCAS_PADRAO[number]['id'];

export interface ConfiguracaoAparencia {
  fundo: string;
  destaque: string;
  segundoFio: string;
  padrao: PadraoAparencia;
  posicao: PosicaoPadrao;
  forca: ForcaPadrao;
  interfaceNova: boolean;
}

const CHAVE_APARENCIA = 'zara-aparencia-v1';
const COR_HEX = /^#[0-9a-f]{6}$/i;

const VARIAVEIS_APARENCIA = [
  '--t-fundo',
  '--t-destaque',
  '--t-segundo',
  '--t-luz',
  '--t-destaque-legivel',
  '--t-sobre-destaque',
] as const;

const ATRIBUTOS_APARENCIA = [
  'data-zara-aparencia',
  'data-zara-tema',
  'data-zara-padrao',
  'data-zara-posicao',
  'data-zara-forca',
] as const;

// A configuração que a ZARA usa quando ninguém escolheu nada.
//
// Alex: "para a configuração padrão escolha você o que achar que mais combina
// com a ZARA e deixe todas as opções customizáveis". Então aqui vai a minha
// escolha, e o motivo de cada uma — porque padrão sem motivo vira gosto de quem
// escreveu por último.
//
//   pele militar      o verde que ele escolheu, na versão mais escura e contida
//   fio diagonal      o padrão mais discreto de todos; lê como superfície
//                     usinada, não como estampa
//   faixa lateral     contido num lugar onde não há texto, como assinatura de
//                     quem fabricou — nunca por cima do conteúdo
//   força sutil       3,5% de opacidade. Se ele notar, está forte demais
//   interface nova    LIGADA: é a que mostra a prova de cada ação, que é o que
//                     a ZARA tem de diferente. Desligar continua a um clique
export const APARENCIA_PADRAO: ConfiguracaoAparencia = {
  fundo: PELES_APARENCIA[0].fundo,
  destaque: PELES_APARENCIA[0].destaque,
  segundoFio: PELES_APARENCIA[0].segundoFio,
  padrao: 'fio-diagonal',
  posicao: 'faixa-lateral',
  forca: 'sutil',
  interfaceNova: true,
};

const pertence = <T extends string>(valor: unknown, opcoes: readonly { id: T }[]): valor is T =>
  typeof valor === 'string' && opcoes.some((opcao) => opcao.id === valor);

const normalizarConfiguracao = (valor: unknown): ConfiguracaoAparencia | null => {
  if (!valor || typeof valor !== 'object') return null;
  const candidato = valor as Record<string, unknown>;
  if (
    typeof candidato.fundo !== 'string' || !COR_HEX.test(candidato.fundo) ||
    typeof candidato.destaque !== 'string' || !COR_HEX.test(candidato.destaque) ||
    typeof candidato.segundoFio !== 'string' || !COR_HEX.test(candidato.segundoFio) ||
    !pertence(candidato.padrao, PADROES_APARENCIA) ||
    !pertence(candidato.posicao, POSICOES_PADRAO) ||
    !pertence(candidato.forca, FORCAS_PADRAO)
  ) return null;

  return {
    fundo: candidato.fundo.toUpperCase(),
    destaque: candidato.destaque.toUpperCase(),
    segundoFio: candidato.segundoFio.toUpperCase(),
    padrao: candidato.padrao,
    posicao: candidato.posicao,
    forca: candidato.forca,
    // Preferências gravadas antes desta visão não têm o campo; desligado
    // preserva exatamente a interface que o Alex já conhecia.
    interfaceNova: typeof candidato.interfaceNova === 'boolean' ? candidato.interfaceNova : false,
  };
};

const luminanciaDaCor = (cor: string): number => {
  const canais = [1, 3, 5].map((inicio) => Number.parseInt(cor.slice(inicio, inicio + 2), 16) / 255);
  const lineares = canais.map((canal) => canal <= 0.03928 ? canal / 12.92 : ((canal + 0.055) / 1.055) ** 2.4);
  return (0.2126 * lineares[0]) + (0.7152 * lineares[1]) + (0.0722 * lineares[2]);
};

const contrasteEntre = (primeira: string, segunda: string): number => {
  const maior = Math.max(luminanciaDaCor(primeira), luminanciaDaCor(segunda));
  const menor = Math.min(luminanciaDaCor(primeira), luminanciaDaCor(segunda));
  return (maior + 0.05) / (menor + 0.05);
};

// A luminância, e não o nome da pele, decide o tema porque as cores livres
// podem transformar qualquer ponto de partida em claro ou escuro.
const temaDaCor = (cor: string): 'claro' | 'escuro' =>
  luminanciaDaCor(cor) > 0.179 ? 'claro' : 'escuro';

export const carregarAparencia = (): ConfiguracaoAparencia | null => {
  try {
    const salvo = window.localStorage.getItem(CHAVE_APARENCIA);
    if (!salvo) return null;
    return normalizarConfiguracao(JSON.parse(salvo));
  } catch {
    return null;
  }
};

export const aplicarAparencia = (configuracao: ConfiguracaoAparencia): boolean => {
  const raiz = document.documentElement;
  const tema = temaDaCor(configuracao.fundo);
  const luz = tema === 'escuro' ? '#EAF0E6' : '#0C0F08';
  const destaqueLegivel = contrasteEntre(configuracao.destaque, configuracao.fundo) >= 4.5
    ? configuracao.destaque
    : luz;
  const sobreDestaque = temaDaCor(configuracao.destaque) === 'escuro' ? '#FFFFFF' : '#090B09';
  raiz.style.setProperty('--t-fundo', configuracao.fundo);
  raiz.style.setProperty('--t-destaque', configuracao.destaque);
  raiz.style.setProperty('--t-segundo', configuracao.segundoFio);
  raiz.style.setProperty('--t-luz', luz);
  raiz.style.setProperty('--t-destaque-legivel', destaqueLegivel);
  raiz.style.setProperty('--t-sobre-destaque', sobreDestaque);
  raiz.dataset.zaraAparencia = 'ativa';
  raiz.dataset.zaraTema = tema;
  raiz.dataset.zaraPadrao = configuracao.padrao;
  raiz.dataset.zaraPosicao = configuracao.posicao;
  raiz.dataset.zaraForca = configuracao.forca;
  return (
    raiz.style.getPropertyValue('--t-fundo') === configuracao.fundo &&
    raiz.style.getPropertyValue('--t-destaque') === configuracao.destaque &&
    raiz.style.getPropertyValue('--t-segundo') === configuracao.segundoFio &&
    raiz.style.getPropertyValue('--t-luz') === luz &&
    raiz.style.getPropertyValue('--t-destaque-legivel') === destaqueLegivel &&
    raiz.style.getPropertyValue('--t-sobre-destaque') === sobreDestaque &&
    raiz.dataset.zaraAparencia === 'ativa' &&
    raiz.dataset.zaraTema === tema &&
    raiz.dataset.zaraPadrao === configuracao.padrao &&
    raiz.dataset.zaraPosicao === configuracao.posicao &&
    raiz.dataset.zaraForca === configuracao.forca
  );
};

export const removerAparencia = (): boolean => {
  const raiz = document.documentElement;
  VARIAVEIS_APARENCIA.forEach((variavel) => raiz.style.removeProperty(variavel));
  ATRIBUTOS_APARENCIA.forEach((atributo) => raiz.removeAttribute(atributo));
  return (
    VARIAVEIS_APARENCIA.every((variavel) => raiz.style.getPropertyValue(variavel) === '') &&
    ATRIBUTOS_APARENCIA.every((atributo) => !raiz.hasAttribute(atributo))
  );
};

export const guardarAparencia = (configuracao: ConfiguracaoAparencia): boolean => {
  try {
    const serializado = JSON.stringify(configuracao);
    window.localStorage.setItem(CHAVE_APARENCIA, serializado);
    return window.localStorage.getItem(CHAVE_APARENCIA) === serializado;
  } catch {
    return false;
  }
};

export const restaurarAparenciaOriginal = (): boolean => {
  const armazenamentoLimpo = (() => {
    try {
      window.localStorage.removeItem(CHAVE_APARENCIA);
      return window.localStorage.getItem(CHAVE_APARENCIA) === null;
    } catch {
      return false;
    }
  })();
  // Mesmo se o armazenamento falhar, a janela deve voltar ao original; nesse
  // caso o retorno falso impede que o painel anuncie uma restauração completa.
  const visualOriginal = removerAparencia();
  return armazenamentoLimpo && visualOriginal;
};

export const encontrarPele = (configuracao: ConfiguracaoAparencia): PeleAparencia | undefined =>
  PELES_APARENCIA.find((pele) =>
    pele.fundo === configuracao.fundo &&
    pele.destaque === configuracao.destaque &&
    pele.segundoFio === configuracao.segundoFio,
  );

// Este módulo entra na árvore de imports antes do createRoot. Aplicar aqui é o
// que restaura a escolha salva antes da primeira pintura, sem flash da original.
export const APARENCIA_INICIAL = carregarAparencia();
export const APARENCIA_INICIAL_VERIFICADA = APARENCIA_INICIAL
  ? aplicarAparencia(APARENCIA_INICIAL)
  : removerAparencia();
