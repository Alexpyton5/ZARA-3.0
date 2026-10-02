import type { MuseReply, MuseSubmission } from './museConversation';
import type { PilotProvider } from './pilotConversation';

export type PilotTurnObservation = {
  event_id: string;
  provider: PilotProvider;
  channel: 'text' | 'voice';
  user_id: string;
  assistant_id: string;
  user_text: string;
  assistant_text: string;
};
export type PilotLearningReceipt = { success: boolean; path?: string };
export type PilotLearningBridge = { learn?: (turn: PilotTurnObservation) => Promise<PilotLearningReceipt> };

/** One observation ID per submission, independent of account-specific DOM IDs.
 * Call only at final completion; callers launch the promise without blocking TTS.
 * A failed retry reuses the ID; the backend independently filters and deduplicates.
 */
export function createPilotTurnRecorder(
  provider: PilotProvider, input: string, channel: 'text' | 'voice', bridge?: PilotLearningBridge,
  newId: () => string = () => globalThis.crypto.randomUUID(),
): (submission: MuseSubmission, reply: MuseReply) => Promise<PilotLearningReceipt> {
  let eventId: string | undefined;
  let pending: Promise<PilotLearningReceipt> | undefined;
  let observed: string | undefined;
  return (submission, reply) => {
    if (!submission.submitted || !submission.confirmed || !submission.userId || !reply.assistantId
      || !reply.text.trim() || reply.busy || !['matched', 'rebound'].includes(reply.correlation || '')
      || !bridge?.learn) return Promise.resolve({ success: false });
    try { eventId ||= newId(); } catch { return Promise.resolve({ success: false }); }
    const turn: PilotTurnObservation = { event_id: eventId, provider, channel, user_id: submission.userId,
      assistant_id: reply.assistantId, user_text: input, assistant_text: reply.text };
    const fingerprint = JSON.stringify(turn);
    if (observed && observed !== fingerprint) return Promise.resolve({ success: false });
    observed = fingerprint;
    if (pending) return pending;
    const attempt = (async (): Promise<PilotLearningReceipt> => {
      try {
        const result = await bridge.learn!(turn);
        return result?.success === true && typeof result.path === 'string' && !!result.path
          ? { success: true, path: result.path } : { success: false };
      } catch { return { success: false }; }
    })();
    pending = attempt;
    void attempt.then(receipt => { if (!receipt.success && pending === attempt) pending = undefined; });
    return attempt;
  };
}
