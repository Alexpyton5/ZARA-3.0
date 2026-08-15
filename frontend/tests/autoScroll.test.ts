import assert from 'node:assert/strict';
import test from 'node:test';

import {
  NEAR_BOTTOM_THRESHOLD,
  initialAutoScrollState,
  isNearBottom,
  onJumpToLatest,
  onMessages,
  onScroll,
} from '../src/renderer/lib/autoScroll';

const atBottom = { scrollTop: 920, scrollHeight: 1000, clientHeight: 80 };
const nearBottom = { scrollTop: 880, scrollHeight: 1000, clientHeight: 80 }; // 40px do fim
const scrolledUp = { scrollTop: 200, scrollHeight: 1000, clientHeight: 80 }; // 720px do fim

test('near-bottom: sticky permanece ligado e nova mensagem rola ao fim', () => {
  let state = onScroll(initialAutoScrollState, nearBottom);
  assert.equal(isNearBottom(nearBottom), true);
  assert.equal(state.sticky, true);
  assert.equal(state.showJumpToLatest, false);

  const r = onMessages(state);
  assert.equal(r.scrollToBottom, true);
  assert.equal(r.state.sticky, true);
  assert.equal(r.state.showJumpToLatest, false);
});

test('exatamente no threshold ainda conta como near-bottom', () => {
  const edge = { scrollTop: 1000 - 80 - NEAR_BOTTOM_THRESHOLD, scrollHeight: 1000, clientHeight: 80 };
  assert.equal(isNearBottom(edge), true);
  const past = { ...edge, scrollTop: edge.scrollTop - 1 };
  assert.equal(isNearBottom(past), false);
});

test('user-scrolled: nova mensagem NAO puxa a viewport e mostra "Ir para ultima mensagem"', () => {
  const state = onScroll(initialAutoScrollState, scrolledUp);
  assert.equal(state.sticky, false);
  assert.equal(state.showJumpToLatest, true);

  const r = onMessages(state);
  assert.equal(r.scrollToBottom, false, 'nao pode rolar enquanto o usuario leu acima');
  assert.equal(r.state.showJumpToLatest, true);
});

test('burst de mensagens enquanto user-scrolled preserva a posicao (nenhum scroll)', () => {
  let state = onScroll(initialAutoScrollState, scrolledUp);
  let scrolls = 0;
  for (let i = 0; i < 25; i += 1) {
    const r = onMessages(state);
    state = r.state;
    if (r.scrollToBottom) scrolls += 1;
  }
  assert.equal(scrolls, 0);
  assert.equal(state.sticky, false);
  assert.equal(state.showJumpToLatest, true);
  // posicao inalterada: o estado nunca pediu scroll, logo scrollTop segue o mesmo
  assert.equal(isNearBottom(scrolledUp), false);
});

test('burst com sticky ligado rola em todas as mensagens', () => {
  let state = onScroll(initialAutoScrollState, atBottom);
  let scrolls = 0;
  for (let i = 0; i < 10; i += 1) {
    const r = onMessages(state);
    state = r.state;
    if (r.scrollToBottom) scrolls += 1;
  }
  assert.equal(scrolls, 10);
});

test('retorno manual ao bottom religa o sticky', () => {
  let state = onScroll(initialAutoScrollState, scrolledUp);
  assert.equal(state.sticky, false);

  state = onScroll(state, atBottom); // usuario rolou de volta
  assert.equal(state.sticky, true);
  assert.equal(state.showJumpToLatest, false);
  assert.equal(onMessages(state).scrollToBottom, true);
});

test('acao "Ir para ultima mensagem" rola e religa o sticky', () => {
  const scrolledState = onScroll(initialAutoScrollState, scrolledUp);
  assert.equal(scrolledState.sticky, false);

  const jump = onJumpToLatest();
  assert.equal(jump.scrollToBottom, true);
  assert.equal(jump.state.sticky, true);
  assert.equal(jump.state.showJumpToLatest, false);
  assert.equal(onMessages(jump.state).scrollToBottom, true);
});

test('container ausente nao quebra e assume fim', () => {
  assert.equal(isNearBottom(null), true);
  assert.equal(isNearBottom(undefined), true);
});
