export interface ReminderEvent {
  id: string
  text: string
  due_at?: number
  fired_at?: number
  state?: string
}

export function normalizeReminderEvent(value: unknown): ReminderEvent | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  const text = typeof record.text === 'string' ? record.text.trim() : ''
  if (!text) return null

  return {
    id: typeof record.id === 'string' ? record.id : '',
    text,
    ...(typeof record.due_at === 'number' ? { due_at: record.due_at } : {}),
    ...(typeof record.fired_at === 'number' ? { fired_at: record.fired_at } : {}),
    ...(typeof record.state === 'string' ? { state: record.state } : {}),
  }
}
