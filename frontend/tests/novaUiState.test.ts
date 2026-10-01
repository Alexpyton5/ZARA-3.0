import test from 'node:test';
import assert from 'node:assert/strict';
import { parseNovaUiState, requireActionResult } from '../src/renderer/lib/novaUiState';

test('a failed snapshot is not shown as an empty, available team', () => {
  assert.throws(() => parseNovaUiState({ success: false, error: 'Backend offline' }), /Backend offline/);
  assert.throws(() => parseNovaUiState({ success: true, projects: [] }), /incompletos/);
});
test('only a confirmed boolean describes pause; real project and result ids are preserved', () => {
  const projects = [{ id: 'session-42', nome: 'Meu projeto', membros: [] }];
  const raw = { success: true, paused: 'false', projects, work: [], activity: [], decisions: [] };
  assert.equal(parseNovaUiState(raw).paused, null);
  assert.deepEqual(parseNovaUiState(raw).projects, projects);
  assert.equal(parseNovaUiState({ ...raw, paused: false }).paused, false);
});
test('actions cannot turn missing or refused responses into success', () => {
  assert.throws(() => requireActionResult(undefined, 'Não confirmado'), /Não confirmado/);
  assert.throws(() => requireActionResult({ success: false, error: 'Recusado' }, 'Não confirmado'), /Recusado/);
  assert.doesNotThrow(() => requireActionResult({ success: true }, 'Não confirmado'));
});
