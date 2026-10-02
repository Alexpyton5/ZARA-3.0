export function errorMessage(error: unknown, fallback = 'Não foi possível concluir. Tente novamente.'): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** All Home actions share the existing backend authorization and result contract. */
export async function executeHomeAction(action: string, params: Record<string, unknown> = {}) {
  const execute = window.zaraIPC?.action?.execute;
  if (!execute) throw new Error('O serviço de ações não está conectado.');
  const response = await execute(action, params);
  const result = response?.result ?? response;
  if (response?.success === false || result?.success !== true) {
    throw new Error(result?.error || response?.error || result?.output || 'A ação não pôde ser confirmada.');
  }
  return result;
}

export function formatDate(value: number | string | null | undefined): string {
  if (!value) return 'Data não informada';
  const date = new Date(typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : value);
  return Number.isNaN(date.getTime()) ? 'Data não informada' : date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}
