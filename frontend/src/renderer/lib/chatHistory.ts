export type ChatRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id?: string;
  role: ChatRole;
  content: string;
  timestamp: number;
}

const roles = new Set<ChatRole>(['user', 'assistant', 'system']);
const maxMessagesFromBackend = 500;
const maxContentChars = 12_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Convert an untrusted IPC response into the renderer's bounded message shape. */
export function normalizeHistoryResponse(response: unknown, fallbackTime = Date.now()): ChatMessage[] {
  if (!isRecord(response) || !Array.isArray(response.messages)) return [];

  const normalized: ChatMessage[] = [];
  for (const [index, candidate] of response.messages.slice(-maxMessagesFromBackend).entries()) {
    if (!isRecord(candidate)) continue;
    const role = candidate.role;
    const content = candidate.content;
    if (typeof role !== 'string' || !roles.has(role as ChatRole)) continue;
    if (typeof content !== 'string' || !content.trim()) continue;

    const rawTimestamp = Number(candidate.timestamp);
    const timestamp = Number.isFinite(rawTimestamp) && rawTimestamp > 0
      ? rawTimestamp
      : fallbackTime + index;
    const id = typeof candidate.id === 'string' && candidate.id.length <= 128
      ? candidate.id
      : undefined;
    normalized.push({
      id,
      role: role as ChatRole,
      content: content.slice(0, maxContentChars),
      timestamp,
    });
  }
  return normalized;
}
