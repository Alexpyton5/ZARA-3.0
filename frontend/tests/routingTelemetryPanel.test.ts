import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const component = readFileSync(
  resolve(process.cwd(), 'src/renderer/components/zara/RoutingTelemetryPanel.tsx'),
  'utf8',
);
const styles = readFileSync(
  resolve(process.cwd(), 'src/renderer/components/zara/RoutingTelemetryPanel.css'),
  'utf8',
);

test('component receives telemetry only through typed props', () => {
  assert.match(component, /interface RoutingTelemetryPanelProps/);
  assert.match(component, /success: boolean/);
  assert.match(component, /latency: number \| null/);
  assert.match(component, /fallback: boolean/);
  assert.match(component, /pendingReview: number/);
  assert.doesNotMatch(component, /fetch\(|window\.electron|ipcRenderer/);
});

test('component exposes empty, error and human-review states accessibly', () => {
  assert.match(component, /role="alert"/);
  assert.match(component, /role="status"/);
  assert.match(component, /aria-labelledby="routing-telemetry-title"/);
  assert.match(component, /Ainda não há decisões de roteamento/);
  assert.match(component, /candidatos pendentes/);
});

test('panel has responsive and reduced-motion styles', () => {
  assert.match(styles, /@media \(max-width: 760px\)/);
  assert.match(styles, /@media \(max-width: 460px\)/);
  assert.match(styles, /prefers-reduced-motion/);
});
