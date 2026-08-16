import React, { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Configurações da aparência da ZARA.
 *
 * Regra que faz isto ser seguro: todo regulador escreve numa variável CSS que a
 * folha do Alex JÁ usa (--accent, --ring, --page, --sidebar...). Não existe tema
 * paralelo por cima; é o tema dele sendo ajustado. Por isso customizar não pode
 * quebrar o desenho — no pior caso ele volta ao padrão num botão.
 *
 * Nada aqui fala com o backend. É só aparência, e vive no localStorage.
 */

export type ModoDeTema = 'claro' | 'escuro' | 'sistema';

export interface Aparencia {
  modo: ModoDeTema;
  fonteLab: number;        // px do texto do Lab e do log
  acento: string;          // cor de destaque (botão de voz, ícones, seleção)
  anel: string;            // cor do anel central
  forcaAnel: number;       // brilho do anel: 0.4 apagado, 2 reluzente
  brilhoAnel: number;      // raio do halo em px
  anelAltura: number;      // sobe/desce em px. So a altura: mexer nos lados
                           // deixaria o circulo torto, e Alex pediu para travar.
  anelTamanho: number;     // 0,6 a 1,4 do tamanho original
  palco: string;           // fundo atrás do anel
  palcoForca: number;      // 0 = invisível, 1 = cheio
  barra: string;           // cor das laterais e dos painéis
  barraOpacidade: number;  // translucidez das laterais
  // Duas logos, dois conjuntos. Mexer numa nao pode mexer na outra.
  logoMatiz: number;       // marca da barra lateral (a de cima do "Hoje")
  logoSaturacao: number;
  logoBrilho: number;
  aguaMatiz: number;       // marca d'agua atras do Lab e do log
  aguaSaturacao: number;
  aguaBrilho: number;
  aguaOpacidade: number;
}

export const APARENCIA_PADRAO: Aparencia = {
  modo: 'escuro',
  fonteLab: 13,
  acento: '#b9cfae',
  anel: '#a8c3a0',
  forcaAnel: 1,
  brilhoAnel: 8,
  anelAltura: -27,
  anelTamanho: 1,
  palco: '#121313',
  palcoForca: 0,
  barra: '#161817',
  barraOpacidade: 0.78,
  logoMatiz: 90, logoSaturacao: 0.55, logoBrilho: 1,
  aguaMatiz: 90, aguaSaturacao: 0.55, aguaBrilho: 1,
  aguaOpacidade: 0.5,
};

// O claro tem outros pontos de partida; senão trocar de modo entrega um tema quebrado.
export const APARENCIA_PADRAO_CLARA: Aparencia = {
  ...APARENCIA_PADRAO,
  modo: 'claro',
  acento: '#533845',
  anel: '#b38a9f',
  palco: '#f3eeea',
  barra: '#f6f1ec',
  barraOpacidade: 0.72,
  logoMatiz: 320, logoSaturacao: 0.35,
  aguaMatiz: 320, aguaSaturacao: 0.35,
  aguaOpacidade: 0.72,
};

const CHAVE = 'zara-aparencia';

function comAlfa(hex: string, alfa: number): string {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, alfa))})`;
}

/**
 * O que fica em disco: o modo atual e UM CONJUNTO POR MODO.
 *
 * Alex: "tem que haver uma configuracao diferente para cada modo e fica salvo e
 * quando alterar o tema nao muda o outro". Antes trocar de modo jogava fora o
 * que ele tinha ajustado naquele modo; agora cada um dorme no proprio quarto.
 */
interface Guardado {
  modo: ModoDeTema;
  claro: Aparencia;
  escuro: Aparencia;
}

const GUARDADO_PADRAO: Guardado = {
  modo: 'escuro',
  claro: APARENCIA_PADRAO_CLARA,
  escuro: APARENCIA_PADRAO,
};

function carregarGuardado(): Guardado {
  try {
    const cru = localStorage.getItem(CHAVE);
    if (!cru) return GUARDADO_PADRAO;
    const salvo = JSON.parse(cru);
    // Formato antigo (um conjunto so): aproveita no modo em que ele estava.
    if (salvo && !salvo.claro && !salvo.escuro && salvo.modo) {
      const qual = salvo.modo === 'claro' ? 'claro' : 'escuro';
      return { ...GUARDADO_PADRAO, modo: salvo.modo,
               [qual]: { ...GUARDADO_PADRAO[qual], ...salvo } } as Guardado;
    }
    return {
      modo: salvo?.modo || 'escuro',
      claro: { ...APARENCIA_PADRAO_CLARA, ...(salvo?.claro || {}) },
      escuro: { ...APARENCIA_PADRAO, ...(salvo?.escuro || {}) },
    };
  } catch {
    return GUARDADO_PADRAO;
  }
}

function modoEfetivo(modo: ModoDeTema): 'claro' | 'escuro' {
  if (modo !== 'sistema') return modo;
  return window.matchMedia?.('(prefers-color-scheme: light)')?.matches ? 'claro' : 'escuro';
}

/** Escreve tudo nas variáveis CSS do elemento raiz da interface. */
export function aplicarAparencia(raiz: HTMLElement | null, a: Aparencia): void {
  if (!raiz) return;
  const s = raiz.style;
  s.setProperty('--accent', a.acento);
  s.setProperty('--accent-soft', comAlfa(a.acento, 0.18));
  s.setProperty('--ring', a.anel);
  s.setProperty('--sidebar', comAlfa(a.barra, a.barraOpacidade));
  s.setProperty('--card', comAlfa(a.barra, Math.max(0.12, a.barraOpacidade * 0.7)));
  s.setProperty('--window', comAlfa(a.barra, Math.min(1, a.barraOpacidade + 0.16)));
  s.setProperty('--zara-fonte-lab', `${a.fonteLab}px`);
  s.setProperty('--zara-anel-forca', String(a.forcaAnel));
  s.setProperty('--zara-anel-brilho', `${a.brilhoAnel}px`);
  s.setProperty('--zara-anel-y', `${a.anelAltura}px`);
  s.setProperty('--zara-anel-tamanho', String(a.anelTamanho));
  s.setProperty('--zara-palco', comAlfa(a.palco, a.palcoForca));
  const receita = (h: number, sat: number, br: number) =>
    `grayscale(1) sepia(1) hue-rotate(${h}deg) saturate(${sat}) brightness(${br})`;
  const padrao = a.modo === 'claro' ? APARENCIA_PADRAO_CLARA : APARENCIA_PADRAO;

  // A marca d'agua nasce FOSCA: preta no escuro, branca quente no claro. Ela so
  // recebe cor quando Alex mexe num dos reguladores dela — antes eu tinha
  // aplicado a receita colorida por padrao e ela ficou verde no tema escuro.
  const fosco = a.modo === 'claro'
    ? 'brightness(0) invert(1) sepia(.32) saturate(.5)'
    : 'brightness(0)';
  const aguaMexida = a.aguaMatiz !== padrao.aguaMatiz
    || a.aguaSaturacao !== padrao.aguaSaturacao
    || a.aguaBrilho !== padrao.aguaBrilho;
  s.setProperty('--zara-agua-filtro', aguaMexida ? receita(a.aguaMatiz, a.aguaSaturacao, a.aguaBrilho) : fosco);

  // A logo da barra lateral e um degrade metalico: colorir por padrao a
  // achataria, entao ela fica intacta ate ele mexer.
  const logoMexida = a.logoMatiz !== padrao.logoMatiz
    || a.logoSaturacao !== padrao.logoSaturacao
    || a.logoBrilho !== padrao.logoBrilho;
  s.setProperty('--zara-logo-filtro', logoMexida ? receita(a.logoMatiz, a.logoSaturacao, a.logoBrilho) : 'none');

  s.setProperty('--zara-agua-opacidade', String(a.aguaOpacidade));
}

interface Props {
  aberto: boolean;
  onFechar: () => void;
  aparencia: Aparencia;
  onMudar: (a: Aparencia) => void;
  onDesfazer: () => void;
  onRefazer: () => void;
  temPassado: boolean;
  temFuturo: boolean;
}

interface RegProps {
  rotulo: string;
  valor: number;
  min: number;
  max: number;
  passo: number;
  sufixo?: string;
  padrao?: number;
  onMudar: (v: number) => void;
}

const Regulador: React.FC<RegProps> = ({ rotulo, valor, min, max, passo, sufixo, padrao, onMudar }) => {
  // O ponto maior marca onde era o padrao. Clicar nele devolve so esta linha,
  // sem mexer no resto — bem mais fino que o "voltar ao padrao" geral.
  const posicao = padrao === undefined ? null : ((padrao - min) / (max - min)) * 100;
  return (
    <label className="config-linha">
      <span>{rotulo}</span>
      <div className="config-trilho">
        <input type="range" min={min} max={max} step={passo} value={valor}
               onChange={(e) => onMudar(Number(e.target.value))}/>
        {posicao !== null && (
          <button type="button" className={`config-padrao ${valor === padrao ? 'no-lugar' : ''}`}
                  style={{ left: `${posicao}%` }}
                  title={`Padrão: ${padrao}${sufixo || ''} — clique para voltar`}
                  aria-label={`Voltar ao padrão desta opção (${padrao}${sufixo || ''})`}
                  onClick={(e) => { e.preventDefault(); onMudar(padrao as number); }}/>
        )}
      </div>
      <small>{valor}{sufixo || ''}</small>
    </label>
  );
};

const Cor: React.FC<{ rotulo: string; valor: string; onMudar: (v: string) => void }> = ({ rotulo, valor, onMudar }) => (
  <label className="config-linha cor">
    <span>{rotulo}</span>
    <input type="color" value={valor} onChange={(e) => onMudar(e.target.value)}/>
    <small>{valor}</small>
  </label>
);

export const PainelConfiguracoes: React.FC<Props> = ({ aberto, onFechar, aparencia, onMudar, onDesfazer, onRefazer, temPassado, temFuturo }) => {
  const trocar = useCallback(<K extends keyof Aparencia>(campo: K, valor: Aparencia[K]) => {
    onMudar({ ...aparencia, [campo]: valor });
  }, [aparencia, onMudar]);

  useEffect(() => {
    if (!aberto) return;
    const aoTeclar = (e: KeyboardEvent) => { if (e.key === 'Escape') onFechar(); };
    window.addEventListener('keydown', aoTeclar);
    return () => window.removeEventListener('keydown', aoTeclar);
  }, [aberto, onFechar]);

  // De onde saem os pontinhos: o padrao do modo em que ele esta.
  const padroes = aparencia.modo === 'claro' ? APARENCIA_PADRAO_CLARA : APARENCIA_PADRAO;

  if (!aberto) return null;

  return (
    <div className="config-fundo" onClick={onFechar}>
      <aside className="config-painel" onClick={(e) => e.stopPropagation()} aria-label="Configurações de aparência">
        <header>
          <strong>Aparência</strong>
          <div className="config-historico">
            <button type="button" onClick={onDesfazer} disabled={!temPassado} title="Desfazer" aria-label="Desfazer">↶</button>
            <button type="button" onClick={onRefazer} disabled={!temFuturo} title="Refazer" aria-label="Refazer">↷</button>
            <button type="button" onClick={onFechar} aria-label="Fechar">×</button>
          </div>
        </header>

        <section>
          <h4>Modo</h4>
          <div className="config-modos">
            {(['claro', 'escuro', 'sistema'] as ModoDeTema[]).map((m) => (
              <button key={m} type="button"
                      className={aparencia.modo === m ? 'marcado' : ''}
                      onClick={() => onMudar({ ...aparencia, modo: m })}>
                {m === 'claro' ? 'Claro' : m === 'escuro' ? 'Escuro' : 'Seguir o Windows'}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h4>Texto</h4>
          <Regulador rotulo="Tamanho no Lab e no log" valor={aparencia.fonteLab} padrao={padroes.fonteLab} min={11} max={20} passo={1} sufixo="px"
                     onMudar={(v) => trocar('fonteLab', v)}/>
        </section>

        <section>
          <h4>Anel</h4>
          <Cor rotulo="Cor" valor={aparencia.anel} onMudar={(v) => trocar('anel', v)}/>
          <Regulador rotulo="Força" valor={aparencia.forcaAnel} padrao={padroes.forcaAnel} min={0.4} max={2} passo={0.05}
                     onMudar={(v) => trocar('forcaAnel', v)}/>
          <Regulador rotulo="Brilho" valor={aparencia.brilhoAnel} padrao={padroes.brilhoAnel} min={0} max={30} passo={1} sufixo="px"
                     onMudar={(v) => trocar('brilhoAnel', v)}/>
          <Regulador rotulo="Altura" valor={aparencia.anelAltura} padrao={padroes.anelAltura} min={-140} max={90} passo={1} sufixo="px"
                     onMudar={(v) => trocar('anelAltura', v)}/>
          <Regulador rotulo="Tamanho" valor={aparencia.anelTamanho} padrao={padroes.anelTamanho} min={0.6} max={1.4} passo={0.01}
                     onMudar={(v) => trocar('anelTamanho', v)}/>
        </section>

        <section>
          <h4>Fundo atrás do anel</h4>
          {/* Escolher a cor com a intensidade em zero nao mudava nada na tela, e
              dava a impressao de que o painel estava quebrado. Escolher a cor
              acende sozinho; a intensidade continua no controle dele. */}
          <Cor rotulo="Cor" valor={aparencia.palco}
               onMudar={(v) => onMudar({ ...aparencia, palco: v,
                 palcoForca: aparencia.palcoForca < 0.05 ? 0.35 : aparencia.palcoForca })}/>
          <Regulador rotulo="Intensidade" valor={aparencia.palcoForca} padrao={padroes.palcoForca} min={0} max={1} passo={0.02}
                     onMudar={(v) => trocar('palcoForca', v)}/>
        </section>

        <section>
          <h4>Laterais e painéis</h4>
          <Cor rotulo="Cor" valor={aparencia.barra} onMudar={(v) => trocar('barra', v)}/>
          <Regulador rotulo="Opacidade" valor={aparencia.barraOpacidade} padrao={padroes.barraOpacidade} min={0.2} max={1} passo={0.02}
                     onMudar={(v) => trocar('barraOpacidade', v)}/>
          <Cor rotulo="Destaque" valor={aparencia.acento} onMudar={(v) => trocar('acento', v)}/>
        </section>

        <section>
          <h4>Logo do início</h4>
          <Regulador rotulo="Cor" valor={aparencia.logoMatiz} padrao={padroes.logoMatiz} min={0} max={360} passo={1} sufixo="°"
                     onMudar={(v) => trocar('logoMatiz', v)}/>
          <Regulador rotulo="Saturação" valor={aparencia.logoSaturacao} padrao={padroes.logoSaturacao} min={0} max={2} passo={0.05}
                     onMudar={(v) => trocar('logoSaturacao', v)}/>
          <Regulador rotulo="Reluzência" valor={aparencia.logoBrilho} padrao={padroes.logoBrilho} min={0.2} max={2.4} passo={0.05}
                     onMudar={(v) => trocar('logoBrilho', v)}/>
        </section>

        <section>
          <h4>Marca d'água do Lab e do log</h4>
          <Regulador rotulo="Cor" valor={aparencia.aguaMatiz} padrao={padroes.aguaMatiz} min={0} max={360} passo={1} sufixo="°"
                     onMudar={(v) => trocar('aguaMatiz', v)}/>
          <Regulador rotulo="Saturação" valor={aparencia.aguaSaturacao} padrao={padroes.aguaSaturacao} min={0} max={2} passo={0.05}
                     onMudar={(v) => trocar('aguaSaturacao', v)}/>
          <Regulador rotulo="Reluzência" valor={aparencia.aguaBrilho} padrao={padroes.aguaBrilho} min={0.2} max={2.4} passo={0.05}
                     onMudar={(v) => trocar('aguaBrilho', v)}/>
          <Regulador rotulo="Intensidade" valor={aparencia.aguaOpacidade} padrao={padroes.aguaOpacidade} min={0} max={1} passo={0.02}
                     onMudar={(v) => trocar('aguaOpacidade', v)}/>
        </section>

        <footer>
          <button type="button" onClick={() => onMudar(
            aparencia.modo === 'claro' ? APARENCIA_PADRAO_CLARA : APARENCIA_PADRAO
          )}>
            Voltar ao padrão
          </button>
        </footer>
      </aside>
    </div>
  );
};

export function usarAparencia() {
  const [guardado, setGuardado] = useState<Guardado>(() => carregarGuardado());
  // Pilhas de desfazer/refazer. Alex: "eu mexi e agora o circulo ta meio feio e
  // nao sei como colocar no lugar". Sem isto, errar a mao e uma viagem sem volta.
  const passado = useRef<Guardado[]>([]);
  const futuro = useRef<Guardado[]>([]);
  const ultimoToque = useRef(0);
  const [versao, setVersao] = useState(0);

  const tema = modoEfetivo(guardado.modo);
  const slot = tema === 'claro' ? 'claro' : 'escuro';
  const aparencia: Aparencia = { ...guardado[slot], modo: guardado.modo };

  const setAparencia = useCallback((nova: Aparencia) => {
    setGuardado((atual) => {
      // Arrastar um regulador dispara dezenas de mudancas por segundo. Sem
      // agrupar, "desfazer" andaria um pixel de cada vez e seria inutil.
      const agora = Date.now();
      const continuacao = agora - ultimoToque.current < 700;
      ultimoToque.current = agora;
      if (!continuacao) {
        passado.current = [...passado.current.slice(-49), atual];
        futuro.current = [];
        setVersao((v) => v + 1);
      }
      if (nova.modo !== atual.modo) return { ...atual, modo: nova.modo };
      const onde = modoEfetivo(atual.modo) === 'claro' ? 'claro' : 'escuro';
      return { ...atual, [onde]: { ...nova } };
    });
  }, []);

  const desfazer = useCallback(() => {
    setGuardado((atual) => {
      const anterior = passado.current.pop();
      if (!anterior) return atual;
      futuro.current = [...futuro.current, atual];
      ultimoToque.current = 0;
      setVersao((v) => v + 1);
      return anterior;
    });
  }, []);

  const refazer = useCallback(() => {
    setGuardado((atual) => {
      const proximo = futuro.current.pop();
      if (!proximo) return atual;
      passado.current = [...passado.current, atual];
      ultimoToque.current = 0;
      setVersao((v) => v + 1);
      return proximo;
    });
  }, []);

  useEffect(() => {
    try { localStorage.setItem(CHAVE, JSON.stringify(guardado)); }
    catch { /* disco cheio nao pode derrubar a UI */ }
  }, [guardado]);

  void versao;   // so existe para redesenhar quando as pilhas mudam
  return {
    aparencia, setAparencia, tema, desfazer, refazer,
    temPassado: passado.current.length > 0,
    temFuturo: futuro.current.length > 0,
  };
}
