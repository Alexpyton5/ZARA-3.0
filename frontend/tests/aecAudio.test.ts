import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

import {
  cortarKore,
  iniciarAudioAec,
  pararAudioAec,
  tocarKore,
} from '../src/renderer/lib/aecAudio';

type FakeTrack = { stopped: boolean; stop: () => void; getSettings: () => { echoCancellation: boolean } };

class FakeAudioContext {
  sampleRate = 48000;
  currentTime = 0;
  destination = {};
  closed = false;
  audioWorklet = { addModule: async (_url: string) => undefined };
  sources: Array<{ started: number; stopped: boolean; stop: () => void }> = [];
  stopCalls = 0;

  createMediaStreamSource(_stream: MediaStream) {
    return { connect: (_node: unknown) => undefined, disconnect: () => undefined };
  }

  createGain() {
    return { gain: { value: 0 }, connect: (_destination: unknown) => undefined };
  }

  createBuffer(_channels: number, length: number, sampleRate: number) {
    return { duration: length / sampleRate, getChannelData: () => new Float32Array(length) };
  }

  createBufferSource() {
    const source = {
      started: 0,
      stopped: false,
      buffer: undefined as unknown,
      onended: undefined as (() => void) | undefined,
      connect: (_destination: unknown) => undefined,
      start: (at: number) => { source.started = at; },
      stop: () => { source.stopped = true; this.stopCalls++; source.onended?.(); },
    };
    this.sources.push(source);
    return source;
  }

  close() {
    this.closed = true;
    return Promise.resolve();
  }
}

class FakeWorkletNode {
  static latest: FakeWorkletNode | null = null;
  port: { onmessage: ((event: MessageEvent<Float32Array>) => void) | null } = { onmessage: null };
  constructor() { FakeWorkletNode.latest = this; }
  connect(_destination: unknown) { return undefined; }
  disconnect() { return undefined; }
}

function installAudioFakes(track: FakeTrack, context: FakeAudioContext) {
  const mediaDevices = { getUserMedia: async (_constraints: MediaStreamConstraints) => ({
    getAudioTracks: () => [track],
    getTracks: () => [track],
  }) };
  Object.assign(globalThis, {
    AudioContext: class { constructor() { return context; } },
    AudioWorkletNode: FakeWorkletNode,
    URL: { createObjectURL: () => 'blob:fake', revokeObjectURL: () => undefined },
    Blob,
    window: {
      navigator: { mediaDevices },
      btoa: (value: string) => Buffer.from(value, 'binary').toString('base64'),
      atob: (value: string) => Buffer.from(value, 'base64').toString('binary'),
    },
  });
}

test('iniciarAudioAec pede echoCancellation e envia PCM quando o worklet recebe audio', async () => {
  const track: FakeTrack = { stopped: false, stop() { this.stopped = true; }, getSettings: () => ({ echoCancellation: true }) };
  const context = new FakeAudioContext();
  installAudioFakes(track, context);
  const sent: string[] = [];

  const result = await iniciarAudioAec((pcm) => sent.push(pcm));

  assert.deepEqual(result, { ok: true, aecAtivo: true });
  FakeWorkletNode.latest?.port.onmessage?.({ data: new Float32Array(2048) } as MessageEvent<Float32Array>);
  assert.equal(sent.length, 1);
  pararAudioAec();
  assert.equal(track.stopped, true);
  assert.equal(context.closed, true);
});

test('falha ao abrir microfone retorna erro observável sem sucesso falso', async () => {
  pararAudioAec();
  Object.assign(globalThis, {
    window: { navigator: { mediaDevices: { getUserMedia: async () => { throw new Error('permission denied'); } } } },
  });

  const result = await iniciarAudioAec(() => undefined);

  assert.equal(result.ok, false);
  assert.equal(result.aecAtivo, false);
  assert.match(result.erro ?? '', /permission denied/);
});

test('tocarKore cria e inicia buffer; cortarKore interrompe a fonte ativa', () => {
  cortarKore();
  const context = new FakeAudioContext();
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  const pcm = Buffer.from([0, 0, 255, 127]).toString('base64');

  tocarKore(pcm, 24000);
  assert.equal(context.sources.length, 1);
  assert.equal(context.sources[0].started, 0);
  cortarKore();
  assert.equal(context.stopCalls, 1);
});

test('ZaraControlCenter limita AEC ao transporte renderer e limpa listeners', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/renderer/components/zara/ZaraControlCenter.tsx'),
    'utf8',
  );

  assert.match(source, /audio_transport !== 'renderer'/);
  assert.match(source, /iniciarAudioAec\(\(pcm\) => window\.zaraIPC\?\.voice\?\.sendMicChunk/);
  assert.match(source, /if \(api\.on\?\.voiceOutputAudio\)/);
  assert.match(source, /if \(data\?\.stop\) \{ cortarKore\(\); return; \}/);
  assert.match(source, /if \(data\?\.pcm\) tocarKore\(data\.pcm, data\.sampleRate \|\| 24000\)/);
  assert.match(source, /offs\.forEach\(\(off\) => off\(\)\)/);
});

test('ZaraControlCenter aborta voz renderer quando AEC retorna ok false', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/renderer/components/zara/ZaraControlCenter.tsx'),
    'utf8',
  );

  assert.match(source, /if \(resultado\?\.audio_transport !== 'renderer'\) return true;/);
  assert.match(
    source,
    /if \(!r\.ok\) \{[\s\S]*?notify\('Não consegui abrir o microfone; a voz não vai ouvir você\.', 'error'\);[\s\S]*?return false;/,
  );
  assert.match(
    source,
    /const aecOk = await ligarAecSePreciso\(result\);\s+if \(!aecOk\) \{\s+await api\.voice\?\.stop\?\.\(\);\s+setVoiceOn\(false\);\s+setState\('STANDBY'\);\s+return;\s+\}[\s\S]{0,260}setVoiceOn\(true\);\s+setState\(result\?\.wake_mode \? 'IDLE' : 'LISTENING'\);/,
  );
  assert.match(
    source,
    /const aecOk = await ligarAecSePreciso\(result\);\s+if \(!aecOk\) \{\s+await window\.zaraIPC\?\.voice\?\.stop\?\.\(\);\s+setVoiceOn\(false\);\s+setState\('STANDBY'\);\s+return;\s+\}[\s\S]{0,220}setVoiceOn\(true\); setState\('LISTENING'\);/,
  );
});