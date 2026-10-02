import test from 'node:test';
import assert from 'node:assert/strict';
import { createPilotTurnRecorder, type PilotLearningBridge } from '../src/renderer/lib/pilotLearning';
import type { MuseSubmission, MuseReply } from '../src/renderer/lib/museConversation';

const submitted: MuseSubmission = { submitted: true, confirmed: true, userId: 'user-one', previousAssistantId: 'old' };
const reply: MuseReply = { assistantId: 'reply-one', text: 'Vou preparar a proposta.', busy: false, correlation: 'matched' };

test('one observed turn is recorded once with original text and final reply, not attached context', async () => {
  const calls: unknown[] = [];
  const bridge: PilotLearningBridge = { learn: async turn => { calls.push(turn); return { success: true, path: 'note.md' }; } };
  const record = createPilotTurnRecorder('muse', 'Planeje a entrega', 'text', bridge, () => 'turn-one');
  await Promise.all([record(submitted, reply), record(submitted, reply)]);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], { event_id: 'turn-one', provider: 'muse', channel: 'text', user_id: 'user-one', assistant_id: 'reply-one',
    user_text: 'Planeje a entrega', assistant_text: 'Vou preparar a proposta.' });
});

test('a failed memory retry uses the same observation ID and cannot be mistaken for saved', async () => {
  const ids: string[] = [];
  const record = createPilotTurnRecorder('muse', 'Plano', 'voice', { learn: async turn => {
    ids.push(turn.event_id);
    if (ids.length === 1) throw new Error('disconnected');
    return { success: true, path: 'same-note.md' };
  } }, () => 'turn-stable');
  assert.equal((await record(submitted, reply)).success, false);
  assert.equal((await record(submitted, reply)).success, true);
  assert.deepEqual(ids, ['turn-stable', 'turn-stable']);
});

test('failed, unconfirmed, partial or uncorrelated turns do not reach the vault', async () => {
  let calls = 0;
  const record = createPilotTurnRecorder('muse', 'Plano', 'voice', { learn: async () => { calls++; return { success: true, path: 'note.md' }; } }, () => 'turn');
  for (const submission of [{ ...submitted, submitted: false }, { ...submitted, confirmed: false }, { ...submitted, userId: '' }]) {
    assert.equal((await record(submission, reply)).success, false);
  }
  for (const response of [{ ...reply, busy: true }, { ...reply, assistantId: '' },
    { ...reply, correlation: undefined }, ...(['missing', 'ambiguous', 'superseded'] as const).map(correlation => ({ ...reply, correlation }))]) {
    assert.equal((await record(submitted, response)).success, false);
  }
  assert.equal(calls, 0);
});

test('old or malformed bridge receipts do not claim successful persistence', async () => {
  for (const receipt of [undefined, {}, { success: true }, { success: false, path: 'note.md' }]) {
    const record = createPilotTurnRecorder('muse', 'Plano', 'text', { learn: async () => receipt as any }, () => 'turn');
    assert.equal((await record(submitted, reply)).success, false);
  }
  assert.equal((await createPilotTurnRecorder('muse', 'Plano', 'text', undefined, () => 'turn')(submitted, reply)).success, false);
});

test('a different final reply cannot reuse a saved receipt for the same observation', async () => {
  let calls = 0;
  const record = createPilotTurnRecorder('muse', 'Plano', 'text', { learn: async () => {
    calls++; return { success: true, path: 'note.md' };
  } }, () => 'same-event');
  assert.equal((await record(submitted, reply)).success, true);
  assert.equal((await record(submitted, { ...reply, text: 'Conteudo diferente.' })).success, false);
  assert.equal(calls, 1);
});

test('an unacknowledged write remains pending without requiring the caller to wait', async () => {
  let started = false;
  const record = createPilotTurnRecorder('muse', 'Plano', 'voice', { learn: () => { started = true; return new Promise(() => {}); } }, () => 'turn');
  const pending = record(submitted, reply);
  assert.equal(started, true);
  assert.equal(record(submitted, reply), pending);
});
