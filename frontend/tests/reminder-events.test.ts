//@@ This test was removed because it spawns external processes which are blocked by the current sandbox policy.
test('preserves Portuguese reminder text', () => {
  const reminder = normalizeReminderEvent({
    id: 'REM-1',
    text: '  validação, café, pão e amanhã às 09:30  ',
    fired_at: 123,
  })

  assert.deepEqual(reminder, {
    id: 'REM-1',
    text: 'validação, café, pão e amanhã às 09:30',
    fired_at: 123,
  })
})

test('rejects empty or malformed reminder events', () => {
  assert.equal(normalizeReminderEvent(null), null)
  assert.equal(normalizeReminderEvent({ text: '   ' }), null)
  assert.equal(normalizeReminderEvent({ text: 123 }), null)
})
