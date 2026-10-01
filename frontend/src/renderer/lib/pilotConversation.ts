import { buildPilotMessage, readMuseReply, submitToMuse, type MuseReply, type MuseSubmission, type MuseWebview } from './museConversation';

export type PilotProvider = 'muse' | 'openai';
export const PILOTS = {
  muse: { nome: 'Muse', url: 'https://muse.ai', partition: 'persist:zoe' },
  openai: { nome: 'OpenAI', url: 'https://chatgpt.com', partition: 'persist:zara-openai' },
} as const;

export function isPilotProvider(value: unknown): value is PilotProvider {
  return value === 'muse' || value === 'openai';
}

export type PilotBridge = {
  command(text: string): Promise<{ handled: boolean; success: boolean; response: string; error?: string }>;
  context(text: string): Promise<{ success: boolean; context: string; error?: string }>;
};

export function checkPilotCancellation(cancelled: () => boolean): void {
  if (cancelled()) throw new Error('A conversa foi interrompida. Confira a resposta na sua conta.');
}

/** Both input paths consult the executor first, then fetch context for this turn. */
export async function preparePilotTurn(text: string, bridge: PilotBridge | undefined, cancelled: () => boolean = () => false, manualFallback?: () => Promise<{ response: string; success: boolean }>): Promise<
  { handled: true; response: string; success: boolean } | { handled: false; text: string; context: string }
> {
  if (!text.trim() || text.length > 4000) throw new Error('Escreva uma mensagem de até 4.000 caracteres.');
  checkPilotCancellation(cancelled);
  if (!bridge?.command || !bridge.context) throw new Error('O executor e o contexto do piloto estão indisponíveis.');
  const command = await bridge.command(text);
  checkPilotCancellation(cancelled);
  if (typeof command?.handled !== 'boolean' || typeof command.success !== 'boolean' || typeof command.response !== 'string') {
    throw new Error('O executor retornou uma resposta inválida.');
  }
  if (command.handled) {
    return { handled: true, success: command.success, response: command.response || command.error || 'O executor não confirmou a ação.' };
  }
  if (!command.success) throw new Error(command.error || 'Não foi possível consultar o executor.');
  if (manualFallback) {
    const result = await manualFallback();
    checkPilotCancellation(cancelled);
    return { handled: true, ...result };
  }
  const result = await bridge.context(text);
  checkPilotCancellation(cancelled);
  if (result?.success !== true || typeof result.context !== 'string') {
    throw new Error(result?.error || 'Não foi possível atualizar o contexto do piloto.');
  }
  return { handled: false, text, context: result.context.slice(0, 1800) };
}

/** Read the signed-in conversation, rather than equating a loaded page with login. */
export async function probePilot(webview: MuseWebview, provider: PilotProvider): Promise<boolean> {
  return Boolean(await webview.executeJavaScript(`(() => {
    const input = document.querySelector(${JSON.stringify(provider === 'muse' ? 'textarea[aria-label="Mensagem"]' : '#prompt-textarea')});
    const log = ${provider === 'muse' ? 'document.querySelector(\'[role="log"]\')' : 'true'};
    const signIn = [...document.querySelectorAll('button,a')].some(el =>
      /^(log in|sign in|entrar|iniciar sessão)$/i.test(el.textContent?.trim() || ''));
    return Boolean(input && log && !signIn);
  })()`));
}

export async function submitToPilot(webview: MuseWebview, provider: PilotProvider, text: string, context?: string, cancelled: () => boolean = () => false): Promise<MuseSubmission> {
  checkPilotCancellation(cancelled);
  if (provider === 'muse') {
    const result = await submitToMuse(webview, text, context);
    checkPilotCancellation(cancelled);
    return result;
  }
  if (!text.trim() || text.length > 4000) throw new Error('Escreva uma mensagem de até 4.000 caracteres.');
  const message = buildPilotMessage(text, context);
  const result = await webview.executeJavaScript(`(async () => {
    const epoch = (globalThis.__zaraPilotTurnEpoch || 0) + 1;
    globalThis.__zaraPilotTurnEpoch = epoch;
    const cancelled = () => globalThis.__zaraPilotTurnEpoch !== epoch;
    const input = document.querySelector('#prompt-textarea');
    const messages = () => [...document.querySelectorAll('[data-message-author-role]')];
    const id = el => el?.getAttribute('data-message-id') || el?.closest('[data-testid^="conversation-turn"]')?.getAttribute('data-testid') || '';
    const previousAssistantId = id(messages().filter(el => el.dataset.messageAuthorRole === 'assistant').at(-1));
    const previousUser = id(messages().filter(el => el.dataset.messageAuthorRole === 'user').at(-1));
    if (!input) return {submitted:false,confirmed:false,userId:'',previousAssistantId,error:'Abra sua conta OpenAI e entre na conversa.'};
    if ((input.value || input.innerText || '').trim()) return {submitted:false,confirmed:false,userId:'',previousAssistantId,error:'Há uma mensagem em edição na sua conta. Envie ou apague antes de continuar.'};
    input.focus();
    if (input.tagName === 'TEXTAREA') {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, ${JSON.stringify(message)});
      input.dispatchEvent(new Event('input', {bubbles:true}));
    } else {
      document.execCommand('insertText', false, ${JSON.stringify(message)});
    }
    await new Promise(resolve => requestAnimationFrame(resolve));
    if (cancelled()) return {submitted:false,confirmed:false,userId:'',previousAssistantId,error:'A conversa foi interrompida.'};
    const button = document.querySelector('[data-testid="send-button"]') || document.querySelector('button[aria-label="Send prompt"],button[aria-label="Enviar mensagem"]');
    if (!button || button.disabled) return {submitted:false,confirmed:false,userId:'',previousAssistantId,error:'A OpenAI ainda está ocupada ou o envio não está disponível.'};
    button.click();
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 100));
      if (cancelled()) return {submitted:true,confirmed:false,userId:'',previousAssistantId,error:'A conversa foi interrompida.'};
      const userId = id(messages().filter(el => el.dataset.messageAuthorRole === 'user').at(-1));
      if (userId && userId !== previousUser) return {submitted:true,confirmed:true,userId,previousAssistantId};
    }
    return {submitted:true,confirmed:false,userId:'',previousAssistantId};
  })()`) as MuseSubmission;
  checkPilotCancellation(cancelled);
  return result;
}

export async function readPilotReply(webview: MuseWebview, provider: PilotProvider, submission: MuseSubmission): Promise<MuseReply> {
  if (provider === 'muse') return readMuseReply(webview, submission);
  return webview.executeJavaScript(`(() => {
    const messages = [...document.querySelectorAll('[data-message-author-role]')];
    const id = el => el?.getAttribute('data-message-id') || el?.closest('[data-testid^="conversation-turn"]')?.getAttribute('data-testid') || '';
    const user = messages.find(el => el.dataset.messageAuthorRole === 'user' && id(el) === ${JSON.stringify(submission.userId)});
    const agent = messages.filter(el => el.dataset.messageAuthorRole === 'assistant' && id(el) !== ${JSON.stringify(submission.previousAssistantId)} && user &&
      (user.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)).at(-1);
    const stop = document.querySelector('[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="Parar de gerar"]');
    return {assistantId:id(agent),text:(agent?.querySelector('.markdown,[data-message-content]')?.innerText || agent?.innerText || agent?.textContent || '').trim(),
      busy:!!stop && !stop.disabled};
  })()`) as Promise<MuseReply>;
}

export async function cancelPilotReply(webview: MuseWebview, provider: PilotProvider): Promise<void> {
  const selector = provider === 'muse' ? 'button[aria-label="Parar"]' : '[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="Parar de gerar"]';
  await webview.executeJavaScript(`(() => { globalThis.__zaraPilotTurnEpoch = (globalThis.__zaraPilotTurnEpoch || 0) + 1; const stop = document.querySelector(${JSON.stringify(selector)}); if (stop && !stop.disabled) stop.click(); })()`);
}

export async function sendPilotMessage(webview: MuseWebview, provider: PilotProvider, text: string, cancelled: () => boolean = () => false, context?: string): Promise<string> {
  const submission = await submitToPilot(webview, provider, text, context, cancelled);
  checkPilotCancellation(cancelled);
  if (!submission.submitted || !submission.confirmed) throw new Error(submission.error || 'O envio não foi confirmado. Confira a conversa na sua conta.');
  let last = '';
  let changedAt = Date.now();
  for (let attempt = 0; attempt < 600; attempt++) {
    checkPilotCancellation(cancelled);
    await new Promise(resolve => setTimeout(resolve, 200));
    checkPilotCancellation(cancelled);
    const reply = await readPilotReply(webview, provider, submission);
    checkPilotCancellation(cancelled);
    if (reply.text !== last) { last = reply.text; changedAt = Date.now(); }
    if (reply.assistantId && last && !reply.busy && Date.now() - changedAt >= 800) return last;
  }
  throw new Error('O piloto demorou a responder. Abra sua conta para acompanhar.');
}
