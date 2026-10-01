// ZARA-AEC-RENDERER-001 — áudio de voz com cancelamento de eco do Chromium.
//
// Por que isto existe: a ZARA se ouvia falar. O alto-falante voltava ao
// microfone, o Gemini Live tratava como fala humana e ela respondia a si mesma.
// Guarda por texto e guarda por tempo falharam — o problema é de sinal, não de
// lógica.
//
// A solução é dar ao AEC do Chromium um sinal de referência: a voz da Kore
// precisa sair pelo MESMO processo que captura o microfone. Por isso captura e
// reprodução moram aqui, no renderer, e não mais em PortAudio no Python.
//
// Medido nesta máquina em 2026-08-13 (Chromium 120):
//   eco cru 0,0122 -> com AEC 0,0012, abaixo do ruído da sala
//   voz do Alex por cima: +21 a +30 dB acima do piso do eco
//   Gemini Live: 0 interrupções no piso do eco, "pare" ainda interrompe
//
// A primeira versão usava ScriptProcessorNode e derrubava o renderer inteiro
// com ACCESS_VIOLATION (exitCode -1073741819): tela preta na cara do Alex. A
// API está depreciada e o próprio Chromium avisa para usar AudioWorklet, que é
// o que está aqui — o processamento roda na thread de áudio e o main thread só
// recebe blocos prontos.

const TAXA_ENVIO = 16000 // o que o Gemini Live espera na entrada
const AMOSTRAS_POR_BLOCO = 2048 // ~43 ms a 48 kHz

// O worklet roda numa thread própria e não enxerga este arquivo, por isso vai
// como texto. Ele só acumula e despacha: nada de conversão pesada aqui dentro,
// porque atrasar a thread de áudio produz estalo.
const CODIGO_WORKLET = `
class CapturaPcm extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buf = new Float32Array(${AMOSTRAS_POR_BLOCO})
    this._n = 0
  }
  process(inputs) {
    const canal = inputs[0] && inputs[0][0]
    if (!canal) return true
    for (let i = 0; i < canal.length; i++) {
      this._buf[this._n++] = canal[i]
      if (this._n === this._buf.length) {
        this.port.postMessage(this._buf.slice(0))
        this._n = 0
      }
    }
    return true
  }
}
registerProcessor('captura-pcm', CapturaPcm)
`

let micCtx: AudioContext | null = null
let micStream: MediaStream | null = null
let micNode: AudioWorkletNode | null = null
let micOrigem: MediaStreamAudioSourceNode | null = null
let abrindo = false

let saidaCtx: AudioContext | null = null
let proximoInicio = 0
let primeiroBlocoKore = true
let tocando: AudioBufferSourceNode[] = []
let retomadaSaida: Promise<void> | null = null
let filaSuspensa: Array<{ pcmBase64: string; taxa: number }> = []
let geracaoSaida = 0
const ouvintesSaida = new Set<(active: boolean) => void>()
let ultimoChunkKoreEm = 0
let chunksKoreNaFala = 0

function registrarChunkKore(pcmBase64: string, taxa: number): void {
  const agora = performance.now()
  const intervaloMs = ultimoChunkKoreEm ? agora - ultimoChunkKoreEm : 0
  ultimoChunkKoreEm = agora
  chunksKoreNaFala += 1
  const bytes = Math.floor(pcmBase64.length * 3 / 4)
  const duracaoMs = taxa > 0 ? (bytes / 2 / taxa) * 1000 : 0
  // Permite correlacionar a chegada dos blocos IPC com a duração que deveria
  // estar no buffer, sem gravar o áudio ou o conteúdo da conversa.
  console.info(`[VOICE_TRACE] stage=KORE_AUDIO_BUFFER chunk=${chunksKoreNaFala} gap_ms=${intervaloMs.toFixed(1)} duration_ms=${duracaoMs.toFixed(1)} queued_ms=${Math.max(0, (proximoInicio - (saidaCtx?.currentTime ?? 0)) * 1000).toFixed(1)}`)
}

export function koreTocando(): boolean { return tocando.length > 0 }
/** Generation completion is not playback completion; wait for the last source. */
export async function aguardarFimKore(): Promise<void> {
  if (retomadaSaida) await retomadaSaida;
  if (!koreTocando()) return;
  await new Promise<void>((resolve, reject) => {
    let unsubscribe = () => {};
    const timer = setTimeout(() => {
      unsubscribe();
      reject(new Error('A reprodução da resposta não terminou.'));
    }, 60000);
    unsubscribe = observarKore(active => {
      if (active) return;
      clearTimeout(timer);
      unsubscribe();
      resolve();
    });
  });
}
export function observarKore(listener: (active: boolean) => void): () => void {
  ouvintesSaida.add(listener)
  listener(koreTocando())
  return () => { ouvintesSaida.delete(listener) }
}
function notificarSaida(): void {
  for (const listener of ouvintesSaida) listener(koreTocando())
}

/** Reamostra para 16 kHz int16, com média dos vizinhos para não criar alias. */
function paraInt16em16k(entrada: Float32Array, taxaOrigem: number): Int16Array {
  const razao = taxaOrigem / TAXA_ENVIO
  const total = Math.floor(entrada.length / razao)
  const saida = new Int16Array(total)
  for (let i = 0; i < total; i++) {
    const inicio = Math.floor(i * razao)
    const fim = Math.min(entrada.length, Math.floor((i + 1) * razao))
    let soma = 0
    let n = 0
    for (let j = inicio; j < fim; j++) {
      soma += entrada[j]
      n++
    }
    const v = n > 0 ? soma / n : 0
    saida[i] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)))
  }
  return saida
}

/** btoa em blocos: espalhar um array grande com spread estoura a pilha. */
function paraBase64(bytes: Uint8Array): string {
  let texto = ''
  const bloco = 8192
  for (let i = 0; i < bytes.length; i += bloco) {
    texto += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + bloco)))
  }
  return window.btoa(texto)
}

/**
 * Abre o microfone com AEC e passa a enviar PCM de 16 kHz.
 * Devolve ok:false quando o navegador nega ou não há dispositivo.
 */
export async function iniciarAudioAec(
  enviar: (pcmBase64: string) => void,
): Promise<{ ok: boolean; aecAtivo: boolean; erro?: string }> {
  // Guarda ANTES do await. Duas chamadas concorrentes passariam pelo teste de
  // micCtx e abririam dois microfones — foi assim que nasceram dois nós de
  // captura no primeiro build.
  if (micCtx || abrindo) return { ok: true, aecAtivo: true }
  abrindo = true

  try {
    micStream = await window.navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        // Desligados de propósito: quem decide o que é fala é o VAD do
        // servidor. Supressão de ruído agressiva mastiga o início da frase.
        noiseSuppression: false,
        autoGainControl: false,
      },
    })

    const trilha = micStream.getAudioTracks()[0]
    const aecAtivo = trilha?.getSettings?.().echoCancellation === true

    const ctx = new AudioContext()
    await ctx.resume()
    const url = URL.createObjectURL(
      new Blob([CODIGO_WORKLET], { type: 'application/javascript' }),
    )
    try {
      await ctx.audioWorklet.addModule(url)
    } finally {
      URL.revokeObjectURL(url)
    }

    const origem = ctx.createMediaStreamSource(micStream)
    const no = new AudioWorkletNode(ctx, 'captura-pcm', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    })

    no.port.onmessage = (evento: MessageEvent<Float32Array>) => {
      try {
        const pcm = paraInt16em16k(evento.data, ctx.sampleRate)
        enviar(paraBase64(new Uint8Array(pcm.buffer)))
      } catch {
        // Falha de envio não pode derrubar a captura: sem isto o microfone
        // morreria em silêncio no primeiro erro de IPC.
      }
    }

    // Ganho zero até o destino: o nó precisa estar ligado à saída para ser
    // processado, e o zero impede que o microfone volte pelo alto-falante —
    // que seria justamente o loop que estamos consertando.
    const mudo = ctx.createGain()
    mudo.gain.value = 0
    origem.connect(no)
    no.connect(mudo)
    mudo.connect(ctx.destination)

    // O clique que abriu o microfone também libera este AudioContext para
    // reprodução. Reutilizá-lo evita criar depois um segundo contexto sem
    // gesto do usuário, que o Chromium pode suspender e cortar a Kore.
    const saidaAnterior = saidaCtx
    micCtx = ctx
    saidaCtx = ctx
    proximoInicio = ctx.currentTime
    primeiroBlocoKore = true
    if (saidaAnterior && saidaAnterior !== ctx) {
      void saidaAnterior.close().catch(() => undefined)
    }
    micOrigem = origem
    micNode = no
    return { ok: true, aecAtivo }
  } catch (erro) {
    try {
      micStream?.getTracks().forEach((t) => t.stop())
    } catch {
      /* stream nunca abriu */
    }
    micStream = null
    return { ok: false, aecAtivo: false, erro: String(erro) }
  } finally {
    abrindo = false
  }
}

export function pararAudioAec(): void {
  cortarKore()
  try {
    if (micNode) micNode.port.onmessage = null
    micNode?.disconnect()
    micOrigem?.disconnect()
  } catch {
    /* já desconectado */
  }
  micNode = null
  micOrigem = null

  try {
    micStream?.getTracks().forEach((t) => t.stop())
  } catch {
    /* stream já encerrado */
  }
  micStream = null

  const ctx = micCtx
  const ctxSaida = saidaCtx
  micCtx = null
  saidaCtx = null
  proximoInicio = 0
  primeiroBlocoKore = true
  try {
    void ctx?.close()
  } catch {
    /* contexto já fechado */
  }
  if (ctxSaida && ctxSaida !== ctx) {
    try {
      void ctxSaida.close()
    } catch {
      /* contexto de saída já fechado */
    }
  }
}

/**
 * Toca um bloco da voz da Kore. É esta reprodução que serve de referência
 * (far-end) para o AEC — se a Kore tocar por fora daqui, o eco volta.
 */
export function tocarKore(pcmBase64: string, taxa: number): void {
  if (!pcmBase64) return
  registrarChunkKore(pcmBase64, taxa)
  if (!saidaCtx) saidaCtx = micCtx ?? new AudioContext()
  const ctx = saidaCtx
  if (ctx.state === 'suspended') {
    // Um único resume drena a fila na ordem em que os blocos chegaram. Além
    // de evitar chamadas concorrentes ao Chromium, a geração impede que uma
    // fala interrompida reapareça quando o resume assíncrono termina depois.
    filaSuspensa.push({ pcmBase64, taxa })
    if (!retomadaSaida) {
      const geracao = geracaoSaida
      const retomada = ctx.resume()
        .then(() => {
          if (geracao !== geracaoSaida || saidaCtx !== ctx) return
          const pendentes = filaSuspensa
          filaSuspensa = []
          for (const item of pendentes) agendarKore(ctx, item.pcmBase64, item.taxa)
        })
        .catch(() => {
          if (geracao === geracaoSaida) cortarKore()
        })
        .finally(() => {
          if (retomadaSaida === retomada) retomadaSaida = null
        })
      retomadaSaida = retomada
    }
    return
  }

  agendarKore(ctx, pcmBase64, taxa)
}

function agendarKore(ctx: AudioContext, pcmBase64: string, taxa: number): void {
  // Um contexto pode fechar entre a chegada do IPC e o agendamento quando a
  // sessão é encerrada. Nesse caso o bloco pertence à sessão antiga.
  if (ctx !== saidaCtx || ctx.state === 'closed') return

  const bruto = window.atob(pcmBase64)
  const amostras = Math.floor(bruto.length / 2)
  if (amostras <= 0) return

  const buffer = ctx.createBuffer(1, amostras, taxa || 24000)
  const canal = buffer.getChannelData(0)
  for (let i = 0; i < amostras; i++) {
    const baixo = bruto.charCodeAt(i * 2)
    const alto = bruto.charCodeAt(i * 2 + 1)
    let v = (alto << 8) | baixo
    if (v >= 0x8000) v -= 0x10000
    canal[i] = v / 32768
  }

  const fonte = ctx.createBufferSource()
  fonte.buffer = buffer
  fonte.connect(ctx.destination)

  // Enfileira em sequência. A folga inicial absorve a variação de chegada;
  // após um underrun, repeti-la acrescentaria silêncio ao atraso da rede.
  const agora = ctx.currentTime
  if (proximoInicio <= agora) {
    if (!primeiroBlocoKore && proximoInicio > 0) {
      console.info(`[VOICE_TRACE] stage=KORE_AUDIO_BUFFER result=UNDERRUN gap_ms=${Math.max(0, (agora - proximoInicio) * 1000).toFixed(1)}`)
    }
    proximoInicio = agora + (primeiroBlocoKore ? 0.10 : 0.005)
  }
  fonte.start(proximoInicio)
  primeiroBlocoKore = false
  proximoInicio += buffer.duration

  tocando.push(fonte)
  notificarSaida()
  fonte.onended = () => {
    tocando = tocando.filter((f) => f !== fonte)
    fonte.disconnect()
    notificarSaida()
  }
}

/**
 * Barge-in: corta a fala da Kore de verdade. Mudar só o estado visual deixaria
 * ela falando por cima do Alex, que é exatamente o que o barge-in impede.
 */
export function cortarKore(): void {
  geracaoSaida += 1
  filaSuspensa = []
  ultimoChunkKoreEm = 0
  chunksKoreNaFala = 0
  retomadaSaida = null
  for (const fonte of tocando) {
    try {
      fonte.stop()
    } catch {
      /* já terminou */
    }
  }
  tocando = []
  proximoInicio = 0
  primeiroBlocoKore = true
  notificarSaida()
}
