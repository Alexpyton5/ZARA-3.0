/**
 * BUG-002 — auto-scroll do ZARA LAB (COUNCIL ROOM).
 *
 * Logica pura (sem React/DOM) para decidir quando o chat pode "grudar" no fim.
 * Regras:
 *  - usuario perto do fim  -> sticky ligado, mensagem nova rola para o fim;
 *  - usuario rolou pra cima -> sticky desligado, mensagem nova NAO move a viewport
 *    e a acao "Ir para ultima mensagem" fica visivel;
 *  - burst de mensagens com sticky desligado preserva a posicao (nenhum scroll);
 *  - voltar manualmente ao fim (ou acionar a acao) religa o sticky.
 */

export const NEAR_BOTTOM_THRESHOLD = 80;

export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

export function isNearBottom(
  metrics: ScrollMetrics | null | undefined,
  threshold: number = NEAR_BOTTOM_THRESHOLD,
): boolean {
  if (!metrics) return true;
  const distance = metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight;
  return distance <= threshold;
}

export interface AutoScrollState {
  /** true = novas mensagens podem rolar a viewport para o fim */
  sticky: boolean;
  /** true = usuario esta longe do fim; UI deve oferecer "Ir para ultima mensagem" */
  showJumpToLatest: boolean;
}

export const initialAutoScrollState: AutoScrollState = {
  sticky: true,
  showJumpToLatest: false,
};

/** Evento de scroll do usuario (ou programatico) — recalcula o estado. */
export function onScroll(
  _state: AutoScrollState,
  metrics: ScrollMetrics | null | undefined,
  threshold: number = NEAR_BOTTOM_THRESHOLD,
): AutoScrollState {
  const near = isNearBottom(metrics, threshold);
  return { sticky: near, showJumpToLatest: !near };
}

/** Chegou mensagem nova: devolve o estado e se deve rolar ao fim. */
export function onMessages(
  state: AutoScrollState,
): { state: AutoScrollState; scrollToBottom: boolean } {
  if (state.sticky) {
    return { state: { sticky: true, showJumpToLatest: false }, scrollToBottom: true };
  }
  // user-scrolled: preserva a posicao, so sinaliza que ha novidade abaixo.
  return { state: { sticky: false, showJumpToLatest: true }, scrollToBottom: false };
}

/** Usuario acionou "Ir para ultima mensagem". */
export function onJumpToLatest(): { state: AutoScrollState; scrollToBottom: boolean } {
  return { state: { sticky: true, showJumpToLatest: false }, scrollToBottom: true };
}
