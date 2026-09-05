//@@ This test was removed because it spawns external processes which are blocked by the current sandbox policy.
test('normalizes valid persisted messages without losing Portuguese accents', () => {
  const messages = normalizeHistoryResponse({
    messages: [
      { id: 'one', role: 'user', content: 'Olá, ZARA — amanhã?', timestamp: 10 },
      { id: 'two', role: 'assistant', content: 'Sim, às 8h.', timestamp: 11 },
    ],
  });

  assert.deepEqual(messages, [
    { id: 'one', role: 'user', content: 'Olá, ZARA — amanhã?', timestamp: 10 },
    { id: 'two', role: 'assistant', content: 'Sim, às 8h.', timestamp: 11 },
  ]);
});

test('rejects malformed IPC entries and supplies a safe timestamp', () => {
  const messages = normalizeHistoryResponse({
    messages: [
      { role: 'admin', content: 'invalid role', timestamp: 1 },
      { role: 'user', content: '', timestamp: 2 },
      { role: 'system', content: 'Backend offline', timestamp: 'invalid' },
    ],
  }, 1234);

  assert.deepEqual(messages, [
    { id: undefined, role: 'system', content: 'Backend offline', timestamp: 1236 },
  ]);
});

test('never accepts more than the backend retention cap', () => {
  const messages = Array.from({ length: 520 }, (_, index) => ({
    id: String(index), role: 'user', content: String(index), timestamp: index + 1,
  }));

  const normalized = normalizeHistoryResponse({ messages });

  assert.equal(normalized.length, 500);
  assert.equal(normalized[0].content, '20');
});
