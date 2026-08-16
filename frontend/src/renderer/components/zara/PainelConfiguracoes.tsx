import React, { useCallback, useEffect, useState } from 'react';

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
  palco: string;           // fundo atrás do anel
  palcoForca: number;      // 0 = invisível, 1 = cheio
  barra: string;           // cor das laterais e dos painéis
  barraOpacidade: number;  // translucidez das laterais
  marcaMatiz: number;      // 0–360, cor das logos
  marcaSaturacao: number;  // 0 = cinza, 2 = saturado
  marcaBrilho: number;     // reluzência
  marcaOpacidade: number;  // quanto a marca d'água aparece
}

export const APARENCIA_PADRAO: Aparencia = {
  modo: 'escuro',
  fonteLab: 13,
  acento: '#b9cfae',
  anel: '#a8c3a0',
  forcaAnel: 1,
  brilhoAnel: 8,
  palco: '#121313',
  palcoForca: 0,
  barra: '#161817',
  barraOpacidade: 0.78,
  marcaMatiz: 90,
  marcaSaturacao: 0.55,
  marcaBrilho: 1,
  marcaOpacidade: 0.5,
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
  marcaMatiz: 320,
  marcaSaturacao: 0.35,
  marcaOpacidade: 0.72,
};

const CHAVE = 'zara-aparencia';

function comAlfa(hex: string, alfa: number): string {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, alfa))})`;
}

export function carregarAparencia(): Aparencia {
  try {
    const cru = localStorage.getItem(CHAVE);
    if (!cru) return APARENCIA_PADRAO;
    const salvo = JSON.parse(cru);
    const base = salvo?.modo === 'claro' ? APARENCIA_PADRAO_CLARA : APARENCIA_PADRAO;
    return { ...base, ...salvo };
  } catch {
    return APARENCIA_PADRAO;
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
  s.setProperty('--zara-palco', comAlfa(a.palco, a.palcoForca));
  const colorir = `grayscale(1) sepia(1) hue-rotate(${a.marcaMatiz}deg) saturate(${a.marcaSaturacao}) brightness(${a.marcaBrilho})`;
  s.setProperty('--zara-marca-filtro', colorir);
  // A logo da barra lateral e um degrade metalico. Colorir por padrao a
  // achataria, entao ela so entra na brincadeira quando Alex mexe de fato num
  // dos tres reguladores de logo.
  const padrao = a.modo === 'claro' ? APARENCIA_PADRAO_CLARA : APARENCIA_PADRAO;
  const mexeu = a.marcaMatiz !== padrao.marcaMatiz
    || a.marcaSaturacao !== padrao.marcaSaturacao
    || a.marcaBrilho !== padrao.marcaBrilho;
  s.setProperty('--zara-marca-brand', mexeu ? colorir : 'none');
  s.setProperty('--zara-marca-opacidade', String(a.marcaOpacidade));
}

interface Props {
  aberto: boolean;
  onFechar: () => void;
  aparencia: Aparencia;
  onMudar: (a: Aparencia) => void;
}

interface RegProps {
  rotulo: string;
  valor: number;
  min: number;
  max: number;
  passo: number;
  sufixo?: string;
  onMudar: (v: number) => void;
}

const Regulador: React.FC<RegProps> = ({ rotulo, valor, min, max, passo, sufixo, onMudar }) => (
  <label className="config-linha">
    <span>{rotulo}</span>
    <input type="range" min={min} max={max} step={passo} value={valor}
           onChange={(e) => onMudar(Number(e.target.value))}/>
    <small>{valor}{sufixo || ''}</small>
  </label>
);

const Cor: React.FC<{ rotulo: string; valor: string; onMudar: (v: string) => void }> = ({ rotulo, valor, onMudar }) => (
  <label className="config-linha cor">
    <span>{rotulo}</span>
    <input type="color" value={valor} onChange={(e) => onMudar(e.target.value)}/>
    <small>{valor}</small>
  </label>
);

export const PainelConfiguracoes: React.FC<Props> = ({ aberto, onFechar, aparencia, onMudar }) => {
  const trocar = useCallback(<K extends keyof Aparencia>(campo: K, valor: Aparencia[K]) => {
    onMudar({ ...aparencia, [campo]: valor });
  }, [aparencia, onMudar]);

  useEffect(() => {
    if (!aberto) return;
    const aoTeclar = (e: KeyboardEvent) => { if (e.key === 'Escape') onFechar(); };
    window.addEventListener('keydown', aoTeclar);
    return () => window.removeEventListener('keydown', aoTeclar);
  }, [aberto, onFechar]);

  if (!aberto) return null;

  return (
    <div className="config-fundo" onClick={onFechar}>
      <aside className="config-painel" onClick={(e) => e.stopPropagation()} aria-label="Configurações de aparência">
        <header>
          <strong>Aparência</strong>
          <button type="button" onClick={onFechar} aria-label="Fechar">×</button>
        </header>

        <section>
          <h4>Modo</h4>
          <div className="config-modos">
            {(['claro', 'escuro', 'sistema'] as ModoDeTema[]).map((m) => (
              <button key={m} type="button"
                      className={aparencia.modo === m ? 'marcado' : ''}
                      onClick={() => onMudar({
                        // Trocar de modo puxa o ponto de partida daquele modo; sem isso
                        // as cores do escuro iam para o claro e ficava ilegível.
                        ...(m === 'claro' ? APARENCIA_PADRAO_CLARA : APARENCIA_PADRAO),
                        modo: m,
                        fonteLab: aparencia.fonteLab,
                      })}>
                {m === 'claro' ? 'Claro' : m === 'escuro' ? 'Escuro' : 'Seguir o Windows'}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h4>Texto</h4>
          <Regulador rotulo="Tamanho no Lab e no log" valor={aparencia.fonteLab} min={11} max={20} passo={1} sufixo="px"
                     onMudar={(v) => trocar('fonteLab', v)}/>
        </section>

        <section>
          <h4>Anel</h4>
          <Cor rotulo="Cor" valor={aparencia.anel} onMudar={(v) => trocar('anel', v)}/>
          <Regulador rotulo="Força" valor={aparencia.forcaAnel} min={0.4} max={2} passo={0.05}
                     onMudar={(v) => trocar('forcaAnel', v)}/>
          <Regulador rotulo="Brilho" valor={aparencia.brilhoAnel} min={0} max={30} passo={1} sufixo="px"
                     onMudar={(v) => trocar('brilhoAnel', v)}/>
        </section>

        <section>
          <h4>Fundo atrás do anel</h4>
          <Cor rotulo="Cor" valor={aparencia.palco} onMudar={(v) => trocar('palco', v)}/>
          <Regulador rotulo="Intensidade" valor={aparencia.palcoForca} min={0} max={1} passo={0.02}
                     onMudar={(v) => trocar('palcoForca', v)}/>
        </section>

        <section>
          <h4>Laterais e painéis</h4>
          <Cor rotulo="Cor" valor={aparencia.barra} onMudar={(v) => trocar('barra', v)}/>
          <Regulador rotulo="Opacidade" valor={aparencia.barraOpacidade} min={0.2} max={1} passo={0.02}
                     onMudar={(v) => trocar('barraOpacidade', v)}/>
          <Cor rotulo="Destaque" valor={aparencia.acento} onMudar={(v) => trocar('acento', v)}/>
        </section>

        <section>
          <h4>Logos</h4>
          <Regulador rotulo="Cor" valor={aparencia.marcaMatiz} min={0} max={360} passo={1} sufixo="°"
                     onMudar={(v) => trocar('marcaMatiz', v)}/>
          <Regulador rotulo="Saturação" valor={aparencia.marcaSaturacao} min={0} max={2} passo={0.05}
                     onMudar={(v) => trocar('marcaSaturacao', v)}/>
          <Regulador rotulo="Reluzência" valor={aparencia.marcaBrilho} min={0.2} max={2.4} passo={0.05}
                     onMudar={(v) => trocar('marcaBrilho', v)}/>
          <Regulador rotulo="Marca d'água" valor={aparencia.marcaOpacidade} min={0} max={1} passo={0.02}
                     onMudar={(v) => trocar('marcaOpacidade', v)}/>
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
  const [aparencia, setAparencia] = useState<Aparencia>(() => carregarAparencia());
  useEffect(() => {
    try { localStorage.setItem(CHAVE, JSON.stringify(aparencia)); } catch { /* disco cheio não pode derrubar a UI */ }
  }, [aparencia]);
  return { aparencia, setAparencia, tema: modoEfetivo(aparencia.modo) };
}
