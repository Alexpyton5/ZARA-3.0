import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

import {
  cortarKore,
  iniciarAudioAec,
  pararAudioAec,
  tocarKore,
  aguardarFimKore,
} from '../src/renderer/lib/aecAudio';

type FakeTrack = { stopped: boolean; stop: () => void; getSettings: () => { echoCancellation: boolean } };

class FakeAudioContext {
  sampleRate = 48000;
  currentTime = 0;
  state: AudioContextState = 'running';
  destination = {};
  closed = false;
  resumeCalls = 0;
  resumeImpl: () => Promise<void> = () => {
    this.state = 'running';
    return Promise.resolve();
  };
  audioWorklet = { addModule: async (_url: string) => undefined };
  sources: Array<{ started: number; stopped: boolean; stop: () => void; onended?: () => void }> = [];
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
      disconnect: () => undefined,
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

  resume() {
    this.resumeCalls++;
    return this.resumeImpl();
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

test('playback completion waits for all scheduled PCM and interruption releases the wait', async () => {
  cortarKore(); pararAudioAec();
  const context = new FakeAudioContext();
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  tocarKore(Buffer.alloc(4800).toString('base64'), 24000);
  tocarKore(Buffer.alloc(4800).toString('base64'), 24000);
  let finished = false;
  const wait = aguardarFimKore().then(() => { finished = true; });
  await Promise.resolve();
  assert.equal(finished, false);
  context.sources[0].onended?.();
  await Promise.resolve();
  assert.equal(finished, false);
  cortarKore();
  await wait;
  assert.equal(finished, true);
  pararAudioAec();
});

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

test('tocarKore reutiliza o contexto desbloqueado do microfone', async () => {
  cortarKore();
  const context = new FakeAudioContext();
  const track = { stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) };
  installAudioFakes(track, context);
  await iniciarAudioAec(() => undefined);
  const pcm = Buffer.from([0, 0, 255, 127]).toString('base64');

  tocarKore(pcm, 24000);
  assert.equal(context.sources.length, 1);
  assert.equal(context.sources[0].started, 0.1);
  cortarKore();
  assert.equal(context.stopCalls, 1);
  pararAudioAec();
});

test('bloco tardio da Kore retoma sem repetir a folga inicial e mantém ordem e corte', () => {
  cortarKore();
  pararAudioAec();
  const context = new FakeAudioContext();
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  // 2400 amostras a 24 kHz = 100 ms; a chegada seguinte ocorre após o fim.
  const pcm = Buffer.alloc(2400 * 2).toString('base64');

  tocarKore(pcm, 24000);
  assert.equal(context.sources[0].started, 0.1);
  context.currentTime = 0.4;
  tocarKore(pcm, 24000);
  tocarKore(pcm, 24000);

  assert.ok(Math.abs(context.sources[1].started - 0.405) < 1e-9);
  assert.ok(Math.abs(context.sources[2].started - 0.505) < 1e-9);
  cortarKore();
  assert.equal(context.stopCalls, 3);
  assert.ok(context.sources.every((source) => source.stopped));
  pararAudioAec();
});

test('tocarKore registra intervalo, duracao e underrun sem gravar PCM', () => {
  cortarKore();
  pararAudioAec();
  const context = new FakeAudioContext();
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  const pcm = Buffer.alloc(2400 * 2).toString('base64');
  const traces: string[] = [];
  const originalInfo = console.info;
  console.info = (line?: unknown) => traces.push(String(line));

  try {
    tocarKore(pcm, 24000);
    context.currentTime = 0.4;
    tocarKore(pcm, 24000);
  } finally {
    console.info = originalInfo;
  }

  assert.match(traces[0], /stage=KORE_AUDIO_BUFFER chunk=1 gap_ms=0\.0 duration_ms=100\.0/);
  assert.match(traces[2], /result=UNDERRUN gap_ms=200\.0/);
  assert.doesNotMatch(traces.join('\n'), /pcm=/i);
  cortarKore();
  pararAudioAec();
});

test('tocarKore espera contexto suspenso retomar antes de agendar audio', async () => {
  cortarKore();
  pararAudioAec();
  const context = new FakeAudioContext();
  context.state = 'suspended';
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  const pcm = Buffer.from([0, 0, 255, 127]).toString('base64');

  tocarKore(pcm, 24000);
  assert.equal(context.sources.length, 0);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(context.resumeCalls, 1);
  assert.equal(context.sources.length, 1);
  cortarKore();
  pararAudioAec();
});

test('blocos suspensos usam um resume e preservam a ordem', async () => {
  cortarKore();
  pararAudioAec();
  const context = new FakeAudioContext();
  context.state = 'suspended';
  let liberar!: () => void;
  context.resumeImpl = () => new Promise<void>((resolve) => {
    liberar = () => { context.state = 'running'; resolve(); };
  });
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  const pcm = Buffer.from([0, 0, 255, 127]).toString('base64');

  tocarKore(pcm, 24000);
  tocarKore(pcm, 24000);
  assert.equal(context.resumeCalls, 1);
  assert.equal(context.sources.length, 0);
  liberar();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(context.sources.length, 2);
  assert.equal(context.sources[0].started, 0.1);
  assert.ok(context.sources[1].started > context.sources[0].started);
  pararAudioAec();
});

test('interrupcao descarta audio que aguardava o contexto retomar', async () => {
  cortarKore();
  pararAudioAec();
  const context = new FakeAudioContext();
  context.state = 'suspended';
  let liberar!: () => void;
  context.resumeImpl = () => new Promise<void>((resolve) => {
    liberar = () => { context.state = 'running'; resolve(); };
  });
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  const pcm = Buffer.from([0, 0, 255, 127]).toString('base64');

  tocarKore(pcm, 24000);
  cortarKore();
  liberar();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(context.sources.length, 0);
  pararAudioAec();
});

test('pararAudioAec fecha contexto de saida mesmo sem microfone renderer', () => {
  cortarKore();
  pararAudioAec();
  const context = new FakeAudioContext();
  installAudioFakes({ stopped: false, stop() {}, getSettings: () => ({ echoCancellation: true }) }, context);
  const pcm = Buffer.from([0, 0, 255, 127]).toString('base64');

  tocarKore(pcm, 24000);
  pararAudioAec();

  assert.equal(context.closed, true);
});

test('VoiceDock limita AEC ao transporte renderer e limpa listeners', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/renderer/components/zara-home/VoiceDock.tsx'),
    'utf8',
  );

  assert.match(source, /response\.mode !== 'local' && response\.audio_transport !== 'local'/);
  assert.match(source, /iniciarAudioAec\(\(pcm\) => window\.zaraIPC\?\.voice\?\.sendMicChunk/);
  assert.match(source, /voiceOutputAudio\?\.\(\(data\) =>/);
  assert.match(source, /if \(data\?\.stop\) cortarKore\(\)/);
  assert.match(source, /else if \(data\?\.pcm\) tocarKore\(data\.pcm, data\.sampleRate \|\| 24000\)/);
  assert.match(source, /unsubscribePlayback\(\)/);
  assert.match(source, /unsubscribe\?\.\(\)/);
});

test('VoiceDock aborta voz renderer quando AEC retorna ok false', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/renderer/components/zara-home/VoiceDock.tsx'),
    'utf8',
  );

  assert.match(
    source,
    /const result = await iniciarAudioAec[\s\S]*?if \(!result\.ok\) throw new Error\('Microfone indisponível/,
  );
  assert.match(source, /catch \(cause\) \{\s+pararAudioAec\(\);[\s\S]*?voice\?\.stop/);
});
