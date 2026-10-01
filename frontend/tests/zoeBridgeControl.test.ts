import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { startZoeBridge } from '../src/zoeBridge';

test('ponte local deixa Zoe executar ação registrada de PC sem chave ou confirmação', async () => {
  const parent = join(process.cwd(), '..', '.zara-dev', 'test-runs');
  mkdirSync(parent, { recursive: true });
  const directory = mkdtempSync(join(parent, 'zara-zoe-bridge-'));
  const calls: Array<{ type: string; payload?: Record<string, unknown> }> = [];
  const dispatch = async (type: string, payload?: Record<string, unknown>) => {
    calls.push({ type, payload });
    if (type === 'action-list') return {
      computer_click: {
        name: 'computer_click', risk: 'HIGH', capability: 'PC_CONTROL',
        requires_confirmation: true,
      },
    };
    return { success: true, result: { success: true, verificado: true } };
  };
  const bridge = await startZoeBridge(directory, dispatch);
  try {
    const { token, port } = JSON.parse(readFileSync(join(directory, 'connection.json'), 'utf8')) as {
      token: string; port: number;
    };
    const post = async (body: unknown, authorization = `Bearer ${token}`) => fetch(`http://127.0.0.1:${port}/v1/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: authorization },
      body: JSON.stringify(body),
    });

    assert.equal((await post({ type: 'action-list' })).status, 200);
    const denied = await post({ type: 'action-execute', payload: {
      action: 'computer_click', params: { x: 12, y: 34 },
    } }, 'Bearer wrong-token');
    assert.equal(denied.status, 401);

    const executed = await post({ type: 'action-execute', payload: {
      action: 'computer_click', params: { x: 12, y: 34 },
    } });
    assert.equal(executed.status, 200);
    assert.equal((await executed.json() as { success: boolean }).success, true);
    assert.deepEqual(calls.at(-1), {
      type: 'action-execute',
      payload: { action: 'computer_click', params: { x: 12, y: 34 } },
    });

    const agent = await post({ type: 'computer-agent-run', payload: { goal: 'feche o bloco de notas' } });
    assert.equal(agent.status, 200);
    assert.deepEqual(calls.at(-1), {
      type: 'computer-agent-run', payload: { goal: 'feche o bloco de notas' },
    });
    const emptyGoal = await post({ type: 'computer-agent-run', payload: { goal: '' } });
    assert.equal(emptyGoal.status, 400);
  } finally {
    await bridge.close();
    rmSync(directory, { recursive: true, force: true });
  }
});
