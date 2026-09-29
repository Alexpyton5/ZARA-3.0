/** Small, visible-client adapter for Alex's signed-in personal Muse conversation. */
export interface MuseWebview {
  executeJavaScript(code: string): Promise<unknown>;
}

export type MuseSubmission = {
  submitted: boolean;
  confirmed: boolean;
  userId: string;
  previousAssistantId: string;
  error?: string;
};

export type MuseReply = {
  assistantId: string;
  text: string;
  busy: boolean;
};

export async function submitToMuse(webview: MuseWebview, rawText: string): Promise<MuseSubmission> {
  const text = rawText.trim();
  if (!text || text.length > 4000) {
    return { submitted: false, confirmed: false, userId: '', previousAssistantId: '', error: 'Frase inválida.' };
  }
  return webview.executeJavaScript(`(async () => {
    const log = document.querySelector('[role="log"]');
    const input = document.querySelector('textarea[aria-label="Mensagem"]');
    if (!log || !input) return {submitted:false,confirmed:false,userId:'',previousAssistantId:'',error:'Conversa da Zoe indisponível.'};
    if (input.value.trim()) return {submitted:false,confirmed:false,userId:'',previousAssistantId:'',error:'Há uma mensagem em edição. Envie ou apague essa mensagem antes da voz.'};
    const previousUser = [...log.querySelectorAll('[data-message-role="user"]')].at(-1)?.getAttribute('data-message-id') || '';
    const previousAssistantId = [...log.querySelectorAll('[data-message-role="assistant"]')].at(-1)?.getAttribute('data-message-id') || '';
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    if (!setter) return {submitted:false,confirmed:false,userId:'',previousAssistantId,error:'Campo de mensagem indisponível.'};
    input.focus();
    setter.call(input, ${JSON.stringify(text)});
    input.dispatchEvent(new Event('input', {bubbles:true}));
    await new Promise(resolve => requestAnimationFrame(resolve));
    const host = input.parentElement?.parentElement?.parentElement;
    const button = host?.querySelector('button[aria-label="Enviar"]');
    if (!button || button.disabled) return {submitted:false,confirmed:false,userId:'',previousAssistantId,error:'Zoe ainda está ocupada ou o envio não ficou pronto.'};
    button.click();
    let userId = '';
    for (let attempt = 0; attempt < 25; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 80));
      const latest = [...log.querySelectorAll('[data-message-role="user"]')].at(-1);
      const id = latest?.getAttribute('data-message-id') || '';
      if (id && id !== previousUser) { userId = id; break; }
    }
    return {submitted:true,confirmed:!!userId,userId,previousAssistantId};
  })()`) as Promise<MuseSubmission>;
}

export async function readMuseReply(
  webview: MuseWebview,
  submission: MuseSubmission,
): Promise<MuseReply> {
  return webview.executeJavaScript(`(() => {
    const log = document.querySelector('[role="log"]');
    if (!log) return {assistantId:'',text:'',busy:false};
    const userId = ${JSON.stringify(submission.userId)};
    const previousAssistantId = ${JSON.stringify(submission.previousAssistantId)};
    const user = [...log.querySelectorAll('[data-message-role="user"]')].find(x => x.getAttribute('data-message-id') === userId);
    const agent = [...log.querySelectorAll('[data-message-role="assistant"]')].filter(x =>
      x.getAttribute('data-message-id') !== previousAssistantId && user &&
      (user.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING)).at(-1);
    const input = document.querySelector('textarea[aria-label="Mensagem"]');
    const composer = input?.parentElement?.parentElement?.parentElement;
    return {
      assistantId: agent?.getAttribute('data-message-id') || '',
      text: agent?.querySelector('.prose')?.innerText?.trim() || '',
      busy: !!composer?.querySelector('button[aria-label="Parar"]'),
    };
  })()`) as Promise<MuseReply>;
}

export function completeSentences(text: string, alreadySpoken: number): { pieces: string[]; consumed: number } {
  const pieces: string[] = [];
  let consumed = alreadySpoken;
  const remaining = text.slice(alreadySpoken);
  // Short clauses can be voiced while Muse is still writing the rest.
  const boundary = /[.!?…](?:\s|$)|[,;:](?:\s|$)|\n\n/g;
  let match: RegExpExecArray | null;
  while ((match = boundary.exec(remaining))) {
    const end = match.index + match[0].length;
    // A tiny clause such as "Olá," would require a separate TTS request and
    // make a short answer slower. Keep it with the next clause instead.
    if (/^[,;:]$/.test(match[0].trim()) && end - (consumed - alreadySpoken) < 28) continue;
    const chunk = remaining.slice(consumed - alreadySpoken, end).trim();
    if (chunk) pieces.push(chunk);
    consumed = alreadySpoken + end;
  }
  return { pieces, consumed };
}

export function stableSpeechPrefix(text: string, alreadySpoken: number, stableMs: number): { piece: string; consumed: number } {
  const remaining = text.slice(alreadySpoken);
  if (stableMs < 300 || remaining.length < 65) return { piece: '', consumed: alreadySpoken };
  const limit = Math.min(remaining.length, 110);
  const cut = remaining.lastIndexOf(' ', limit);
  if (cut < 45) return { piece: '', consumed: alreadySpoken };
  return { piece: remaining.slice(0, cut).trim(), consumed: alreadySpoken + cut + 1 };
}
