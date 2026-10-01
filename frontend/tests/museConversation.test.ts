import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { cancelPilotReply, sendPilotMessage, submitToPilot } from '../src/renderer/lib/pilotConversation';
import { readMuseReply } from '../src/renderer/lib/museConversation';

function composerPage(provider: 'muse' | 'openai', draft = '') {
  let sent = 0;
  const frames: Array<() => void> = [];
  const timers: Array<() => void> = [];
  class Textarea {
    private text = draft;
    get value() { return this.text; }
    set value(value: string) { this.text = value; }
    tagName = 'TEXTAREA';
    focus() {} dispatchEvent() {}
    parentElement: any;
  }
  const input = new Textarea();
  const send = { disabled: false, click: () => { sent++; } };
  const host = { querySelector: () => send };
  input.parentElement = { parentElement: { parentElement: host } };
  const log = { querySelectorAll: () => [] };
  const document = {
    querySelectorAll: () => [],
    querySelector: (selector: string) => {
      if (selector === '[role="log"]') return log;
      if (selector === '#prompt-textarea' || selector === 'textarea[aria-label="Mensagem"]') return input;
      if (selector === '[data-testid="send-button"]') return send;
      return undefined;
    },
  };
  const context = vm.createContext({
    document, HTMLTextAreaElement: Textarea, Event: class {},
    requestAnimationFrame: (callback: () => void) => frames.push(callback),
    setTimeout: (callback: () => void) => timers.push(callback),
  });
  const webview = { executeJavaScript: async (code: string) => vm.runInContext(code, context) };
  const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
  return { provider, webview, input, frames, timers, flush, sent: () => sent };
}

test('cancelling during the composer animation frame prevents a delayed send in both providers', async () => {
  for (const provider of ['muse', 'openai'] as const) {
    const page = composerPage(provider);
    const submitting = submitToPilot(page.webview, provider, 'Oi', 'fresh');
    await page.flush();
    assert.equal(page.frames.length, 1);
    await cancelPilotReply(page.webview, provider);
    page.frames.shift()!();
    const result = await submitting;
    assert.equal(result.submitted, false);
    assert.equal(page.sent(), 0);
  }
});

test('cancelling after a send never retries and returns unconfirmed rather than an old conversation', async () => {
  for (const provider of ['muse', 'openai'] as const) {
    const page = composerPage(provider);
    const submitting = submitToPilot(page.webview, provider, 'Oi');
    await page.flush();
    page.frames.shift()!();
    await page.flush();
    assert.equal(page.sent(), 1);
    await cancelPilotReply(page.webview, provider);
    page.timers.shift()!();
    const result = await submitting;
    assert.equal(result.submitted, true);
    assert.equal(result.confirmed, false);
    assert.equal(page.sent(), 1);
  }
});

test('both adapters preserve the owner draft and do not click send', async () => {
  for (const provider of ['muse', 'openai'] as const) {
    const page = composerPage(provider, 'rascunho do Alex');
    const result = await submitToPilot(page.webview, provider, 'voice text', 'context');
    assert.equal(result.submitted, false);
    assert.equal(page.input.value, 'rascunho do Alex');
    assert.equal(page.sent(), 0);
  }
});

test('Muse reply reader captures visible assistant text after the composer disappears', async () => {
  const user = { getAttribute: (name: string) => name === 'data-message-id' ? 'user-new' : null,
    compareDocumentPosition: (other: unknown) => other === assistant ? 4 : 0 };
  const assistant = { getAttribute: (name: string) => name === 'data-message-id' ? 'assistant-new' : null,
    querySelector: () => null, innerText: 'Oi Alex!' };
  const log = { querySelectorAll: (selector: string) => selector.endsWith('user"]') ? [user] : [assistant] };
  const document = { querySelector: (selector: string) => selector === '[role="log"]' ? log : null };
  const context = vm.createContext({ document, Node: { DOCUMENT_POSITION_FOLLOWING: 4 } });
  const webview = { executeJavaScript: async (code: string) => vm.runInContext(code, context) };
  const result = await readMuseReply(webview, {
    submitted: true, confirmed: true, userId: 'user-new', previousAssistantId: 'assistant-old',
  });
  assert.equal(result.assistantId, 'assistant-new');
  assert.equal(result.text, 'Oi Alex!');
  assert.equal(result.busy, false);
});

test('Muse reply reader stays busy only while a visible stop-generation control is active', async () => {
  const assistant = { getAttribute: () => 'assistant-new', querySelector: () => null, innerText: 'Olá!' };
  const user = { getAttribute: () => 'user-new', compareDocumentPosition: () => 4 };
  const log = { querySelectorAll: (selector: string) => selector.includes('user') ? [user] : [assistant] };
  for (const disabled of [false, true]) {
    const stop = { disabled };
    const document = { querySelector: (selector: string) => selector === '[role="log"]' ? log : stop };
    const context = vm.createContext({ document, Node: { DOCUMENT_POSITION_FOLLOWING: 4 } });
    const result = await readMuseReply({ executeJavaScript: async code => vm.runInContext(code, context) }, {
      submitted: true, confirmed: true, userId: 'user-new', previousAssistantId: 'assistant-old',
    });
    assert.equal(result.busy, !disabled);
  }
});

test('voice/text bridge returns the stable visible Muse answer instead of waiting for a missing composer', async () => {
  let reads = 0;
  const result = await sendPilotMessage({ executeJavaScript: async () => {
    reads++;
    if (reads === 1) return { submitted: true, confirmed: true, userId: 'u-new', previousAssistantId: 'a-old' };
    return { assistantId: 'a-new', text: 'Oi Alex!', busy: false };
  } }, 'muse', 'Oi');
  assert.equal(result, 'Oi Alex!');
  assert.ok(reads >= 6);
});

test('Muse text reply is preserved when a separate audio presentation follows it', async () => {
  const user = { getAttribute: () => 'user-new', compareDocumentPosition: () => 4 };
  const text = { getAttribute: (name: string) => name === 'data-message-id' ? 'answer-text' : null,
    querySelector: (selector: string) => selector.includes('.prose') ? { innerText: 'Oi, Alex!' } : null,
    innerText: 'Oi, Alex!' };
  const audio = { getAttribute: (name: string) => name === 'data-message-id' ? 'answer-audio'
    : name === 'data-message-has-presentation' ? 'true' : null,
    querySelector: (selector: string) => selector.includes('button[aria-label="Reproduzir"]') ? {} : null,
    innerText: '0:00' };
  const log = { querySelectorAll: (selector: string) => selector.includes('user') ? [user] : [text, audio] };
  const document = { querySelector: (selector: string) => selector === '[role="log"]' ? log : null };
  const context = vm.createContext({ document, Node: { DOCUMENT_POSITION_FOLLOWING: 4 } });
  const result = await readMuseReply({ executeJavaScript: async code => vm.runInContext(code, context) }, {
    submitted: true, confirmed: true, userId: 'user-new', previousAssistantId: 'old',
  });
  assert.equal(result.assistantId, 'answer-text');
  assert.equal(result.text, 'Oi, Alex!');
});

test('Muse audio controls alone are never spoken as an assistant answer', async () => {
  const user = { getAttribute: () => 'user-new', compareDocumentPosition: () => 4 };
  const audio = { getAttribute: (name: string) => name === 'data-message-id' ? 'answer-audio'
    : name === 'data-message-has-presentation' ? 'true' : null,
    querySelector: () => null, innerText: '0:00' };
  const log = { querySelectorAll: (selector: string) => selector.includes('user') ? [user] : [audio] };
  const document = { querySelector: (selector: string) => selector === '[role="log"]' ? log : null };
  const context = vm.createContext({ document, Node: { DOCUMENT_POSITION_FOLLOWING: 4 } });
  const result = await readMuseReply({ executeJavaScript: async code => vm.runInContext(code, context) }, {
    submitted: true, confirmed: true, userId: 'user-new', previousAssistantId: 'old',
  });
  assert.equal(result.text, '');
});

function reconciledReplyPage(messages: Array<{ id: string; role: string; text: string }>, epoch = 7) {
  const nodes: any[] = messages.map(message => ({
    getAttribute: (name: string) => name === 'data-message-id' ? message.id : null,
    innerText: message.text,
    querySelector: (selector: string) => selector.includes('.prose') && message.role === 'assistant'
      ? { innerText: message.text } : selector === 'p' ? { textContent: message.text } : null,
    compareDocumentPosition: (other: unknown) => nodes.indexOf(other) > nodes.indexOf(nodeFor(message.id)) ? 4 : 2,
  }));
  const nodeFor = (id: string) => nodes[messages.findIndex(message => message.id === id)];
  const log = { querySelectorAll: (selector: string) => nodes.filter((_node, index) =>
    selector.includes(`"${messages[index].role}"`)) };
  const document = { querySelector: (selector: string) => selector === '[role="log"]' ? log : null };
  const context = vm.createContext({ document, __zaraPilotTurnEpoch: epoch,
    Node: { DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 } });
  return { executeJavaScript: async (code: string) => vm.runInContext(code, context) };
}

const reconciledReceipt = {
  submitted: true, confirmed: true, userId: 'optimistic-user', previousAssistantId: 'old-answer',
  existingUserIds: ['old-user'], messageText: 'Olá.', turnEpoch: 7,
};

test('Muse reply follows the same sent turn after an optimistic user ID is replaced', async () => {
  const result = await readMuseReply(reconciledReplyPage([
    { id: 'old-user', role: 'user', text: 'Olá.' },
    { id: 'old-answer', role: 'assistant', text: 'Resposta antiga.' },
    { id: 'server-user', role: 'user', text: 'Olá.' },
    { id: 'new-answer', role: 'assistant', text: 'Olá, Alex!' },
  ]), reconciledReceipt);
  assert.equal(result.text, 'Olá, Alex!');
  assert.equal(result.assistantId, 'new-answer');
});

test('Muse ID recovery never binds an old greeting, a changed utterance, or an ambiguous later user', async () => {
  for (const following of [
    [],
    [{ id: 'server-user', role: 'user', text: 'Outra pergunta.' }],
    [{ id: 'server-user', role: 'user', text: 'Olá.' }, { id: 'later-user', role: 'user', text: 'Olá.' }],
  ]) {
    const result = await readMuseReply(reconciledReplyPage([
      { id: 'old-user', role: 'user', text: 'Olá.' },
      { id: 'old-answer', role: 'assistant', text: 'Resposta antiga.' },
      ...following, { id: 'unrelated-answer', role: 'assistant', text: 'Não leia.' },
    ]), reconciledReceipt);
    assert.equal(result.text, '');
  }
});

test('an obsolete Muse receipt cannot recover a user after cancellation or a new turn', async () => {
  const result = await readMuseReply(reconciledReplyPage([
    { id: 'server-user', role: 'user', text: 'Olá.' },
    { id: 'new-answer', role: 'assistant', text: 'Não leia.' },
  ], 8), reconciledReceipt);
  assert.equal(result.text, '');
});

test('Muse reply is bounded by the next user turn and cannot read its later answer', async () => {
  const result = await readMuseReply(reconciledReplyPage([
    { id: 'optimistic-user', role: 'user', text: 'Olá.' },
    { id: 'own-answer', role: 'assistant', text: 'Minha resposta.' },
    { id: 'later-user', role: 'user', text: 'Outra pergunta.' },
    { id: 'later-answer', role: 'assistant', text: 'Não leia.' },
  ]), reconciledReceipt);
  assert.equal(result.text, 'Minha resposta.');
});
