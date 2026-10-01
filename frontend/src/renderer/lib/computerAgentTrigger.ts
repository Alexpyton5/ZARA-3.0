/**
 * Gatilho "use o computador para ..." do chat (Frente B).
 *
 * Quando o usuário digita "use o computador para <goal>" no chat, o frontend
 * NÃO envia como mensagem de conversa: ele dispara `computer-agent-run`
 * com o goal para o backend (ver computerAgentBridge.ts).
 *
 * Módulo puro e testável: não toca em window, React ou IPC.
 */

/** Prefixo do gatilho, como o usuário digita (case-insensitive). */
export const COMPUTER_TRIGGER_PREFIX = 'use o computador para';

/**
 * Regex do gatilho: tem que estar no INÍCIO da mensagem (ignora espaços
 * antes), seguido de espaço ou fim de texto. Case-insensitive.
 */
const TRIGGER_RE = /^\s*use o computador para(?=\s|$)/i;

/**
 * Extrai o objetivo (goal) quando a mensagem é o gatilho do use-computer.
 * - Retorna `null` quando NÃO é gatilho (mensagem de chat normal).
 * - Retorna a string do goal (podendo ser '') quando É gatilho.
 */
export function extractComputerGoal(message: string): string | null {
  const match = TRIGGER_RE.exec(message);
  if (!match) return null;
  return message.slice(match[0].length).trim();
}

/** `true` quando a mensagem aciona o use-computer (com ou sem goal). */
export function isComputerAgentTrigger(message: string): boolean {
  return TRIGGER_RE.test(message);
}

/** Spoken commands in the Zoe tab can use natural imperative PT-BR. */
export function extractZoeComputerGoal(message: string): string | null {
  const spoken = message.trim().replace(/^(?:zoe|zara)[,\s]+/i, '').trim();
  const explicit = extractComputerGoal(spoken);
  if (explicit !== null) return explicit;
  return /^(?:abra|abre|abrir|feche|fecha|fechar|clique|clica|click|digite|digita|escreva|escreve|pressione|aperte|role|rola|traga|coloque|aguarde|espere)\b/i.test(spoken)
    ? spoken : null;
}
