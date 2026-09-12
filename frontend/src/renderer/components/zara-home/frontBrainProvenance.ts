export const FRONT_BRAIN_ENGINES = new Set([
  'gpt-5.6-luna',
  'gpt-6-astra',
  'gpt-5.6-sol',
  'gpt-5.6-terra',
]);

/** Accept only a positively identified deterministic result or a factual Run receipt. */
export function validateFrontBrainProvenance(response: any, selected: string): void {
  if (!response || typeof response !== 'object') {
    throw new Error('A resposta chegou sem origem factual.');
  }

  if (response.response_origin === 'local_deterministic') {
    if (typeof response.engine !== 'string' || !response.engine || FRONT_BRAIN_ENGINES.has(response.engine)) {
      throw new Error('A resposta local chegou com uma origem incompatível.');
    }
    return;
  }

  if (response.response_origin === 'front_brain_policy' && response.success === false
      && typeof response.error === 'string' && response.error) {
    throw new Error(response.error);
  }

  if (response.response_origin !== 'front_brain_run') {
    throw new Error('A resposta não prova se veio de uma ação local ou de um modelo.');
  }
  if (response.engine !== selected) {
    throw new Error(`O backend respondeu com ${String(response.engine)} em vez de ${selected}.`);
  }
  if (typeof response.run_id !== 'string' || !response.run_id
      || response.model_requested !== selected
      || typeof response.provider !== 'string' || !response.provider) {
    throw new Error('A resposta chegou sem proveniência factual do cérebro.');
  }
  const reported = response.model_reported;
  if (reported !== null && typeof reported !== 'string') {
    throw new Error('O provedor retornou uma proveniência inválida.');
  }
  const expectedStatus = reported === null ? 'UNREPORTED'
    : reported === response.model_requested ? 'MATCHED' : 'MISMATCH_REJECTED';
  if (response.provenance_status !== expectedStatus
      || (reported !== null && reported !== response.model_requested)) {
    throw new Error(`O provedor respondeu como ${String(reported)}; a resposta foi rejeitada.`);
  }
}
