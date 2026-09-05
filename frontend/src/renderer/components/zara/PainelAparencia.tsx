import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Check, Palette, RotateCcw, Save, X } from 'lucide-react';
import {
  APARENCIA_PADRAO,
  APARENCIA_INICIAL,
  APARENCIA_INICIAL_VERIFICADA,
  ConfiguracaoAparencia,
  FORCAS_PADRAO,
  PADROES_APARENCIA,
  PELES_APARENCIA,
  POSICOES_PADRAO,
  aplicarAparencia,
  encontrarPele,
  guardarAparencia,
  removerAparencia,
  restaurarAparenciaOriginal,
} from '../../lib/aparencia';
import '../../styles/aparencia.css';

interface Props {
  aberto: boolean;
  onClose: () => void;
  onInterfaceNovaChange: (ativa: boolean) => void;
}

type EstadoPersistencia =
  | { tipo: 'neutro'; texto: string }
  | { tipo: 'verificado'; texto: string }
  | { tipo: 'nao-verificado'; texto: string };

const ESTADO_INICIAL: EstadoPersistencia = {
  tipo: 'neutro',
  texto: 'Alterações ao vivo · ainda não guardadas',
};

const ESTADO_CARREGADO: EstadoPersistencia = APARENCIA_INICIAL_VERIFICADA
  ? {
      tipo: 'verificado',
      texto: APARENCIA_INICIAL
        ? 'Escolha guardada reaplicada e verificada'
        : 'Aparência original ativa e verificada',
    }
  : { tipo: 'nao-verificado', texto: 'Aparência inicial não verificada' };

export const PainelAparencia: React.FC<Props> = ({ aberto, onClose, onInterfaceNovaChange }) => {
  const painelRef = useRef<HTMLElement>(null);
  const fecharRef = useRef<HTMLButtonElement>(null);
  const [configuracao, setConfiguracao] = useState<ConfiguracaoAparencia>(() => ({
    ...(APARENCIA_INICIAL ?? APARENCIA_PADRAO),
  }));
  const [aparenciaOriginal, setAparenciaOriginal] = useState(APARENCIA_INICIAL === null);
  const [persistencia, setPersistencia] = useState<EstadoPersistencia>(ESTADO_CARREGADO);
  const peleAtiva = useMemo(
    () => aparenciaOriginal ? undefined : encontrarPele(configuracao)?.id,
    [aparenciaOriginal, configuracao],
  );

  // O layout effect mantém painel e janela no mesmo quadro visual; a primeira
  // carga já foi antecipada no módulo para acontecer antes do React pintar.
  useLayoutEffect(() => {
    if (aparenciaOriginal) void removerAparencia();
    else void aplicarAparencia(configuracao);
  }, [aparenciaOriginal, configuracao]);

  useEffect(() => {
    if (!aberto) return undefined;
    const focoAnterior = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    fecharRef.current?.focus();

    const controlarTeclado = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') {
        evento.preventDefault();
        onClose();
        return;
      }
      if (evento.key !== 'Tab') return;

      const interativos = Array.from(
        painelRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled])') ?? [],
      ).filter((elemento) => elemento.getClientRects().length > 0);
      if (interativos.length === 0) {
        evento.preventDefault();
        painelRef.current?.focus();
        return;
      }

      const primeiro = interativos[0];
      const ultimo = interativos[interativos.length - 1];
      const focoEstaNoPainel = painelRef.current?.contains(document.activeElement) ?? false;
      if (evento.shiftKey && (document.activeElement === primeiro || !focoEstaNoPainel)) {
        evento.preventDefault();
        ultimo.focus();
      } else if (!evento.shiftKey && (document.activeElement === ultimo || !focoEstaNoPainel)) {
        evento.preventDefault();
        primeiro.focus();
      }
    };
    window.addEventListener('keydown', controlarTeclado);
    return () => {
      window.removeEventListener('keydown', controlarTeclado);
      if (focoAnterior?.isConnected) focoAnterior.focus();
    };
  }, [aberto, onClose]);

  const atualizar = (mudanca: Partial<ConfiguracaoAparencia>) => {
    setConfiguracao((atual) => ({ ...atual, ...mudanca }));
    setAparenciaOriginal(false);
    setPersistencia(ESTADO_INICIAL);
    // A troca precisa aparecer antes de guardar para o casal comparar as duas
    // visões; a persistência continua obedecendo ao botão GUARDAR.
    if (typeof mudanca.interfaceNova === 'boolean') onInterfaceNovaChange(mudanca.interfaceNova);
  };

  const escolherPele = (id: string) => {
    const pele = PELES_APARENCIA.find((item) => item.id === id);
    if (!pele) return;
    atualizar({ fundo: pele.fundo, destaque: pele.destaque, segundoFio: pele.segundoFio });
  };

  const guardar = () => {
    if (aparenciaOriginal) {
      const verificado = restaurarAparenciaOriginal();
      setPersistencia(verificado
        ? { tipo: 'verificado', texto: 'Aparência original mantida e verificada' }
        : { tipo: 'nao-verificado', texto: 'Aparência original não verificada' });
      return;
    }

    const visualVerificado = aplicarAparencia(configuracao);
    const armazenamentoVerificado = visualVerificado && guardarAparencia(configuracao);
    setPersistencia(visualVerificado && armazenamentoVerificado
      ? { tipo: 'verificado', texto: 'Escolha guardada neste computador' }
      : { tipo: 'nao-verificado', texto: 'Aplicação ou gravação não verificada' });
  };

  const restaurar = () => {
    const padrao = { ...APARENCIA_PADRAO };
    setConfiguracao(padrao);
    setAparenciaOriginal(true);
    onInterfaceNovaChange(false);
    const verificado = restaurarAparenciaOriginal();
    setPersistencia(verificado
      ? { tipo: 'verificado', texto: 'Aparência original restaurada e verificada' }
      : { tipo: 'nao-verificado', texto: 'Restauração do original não verificada' });
  };

  if (!aberto) return null;

  return (
    <div className="aparencia-backdrop" onMouseDown={(evento) => evento.target === evento.currentTarget && onClose()}>
      <section
        ref={painelRef}
        className="aparencia-painel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="aparencia-dialogo-titulo"
        aria-describedby="aparencia-dialogo-descricao"
        tabIndex={-1}
      >
        <header className="aparencia-cabecalho">
          <div>
            <Palette size={18}/>
            <span id="aparencia-dialogo-titulo">APARÊNCIA</span>
            <small id="aparencia-dialogo-descricao">Escolham juntos. Nada muda para sempre até guardar.</small>
          </div>
          <button ref={fecharRef} type="button" onClick={onClose} aria-label="Fechar painel de aparência"><X size={18}/></button>
        </header>

        <div className="aparencia-conteudo">
          <section className="aparencia-bloco aparencia-peles" aria-labelledby="aparencia-titulo">
            <div className="aparencia-titulo-bloco">
              <span>01</span>
              <div><h2 id="aparencia-titulo">PELE</h2><p>Treze pontos de partida. Depois, qualquer cor.</p></div>
            </div>
            <div className="aparencia-grade-peles">
              {PELES_APARENCIA.map((pele) => (
                <button
                  type="button"
                  key={pele.id}
                  className={peleAtiva === pele.id ? 'ativa' : ''}
                  onClick={() => escolherPele(pele.id)}
                  aria-pressed={peleAtiva === pele.id}
                >
                  <span className="aparencia-amostra-pele" style={{ backgroundColor: pele.fundo }}>
                    <i style={{ backgroundColor: pele.destaque }}/>
                    <b style={{ backgroundColor: pele.segundoFio }}/>
                  </span>
                  <strong>{pele.nome}</strong>
                  <small>{pele.fundo}</small>
                  {peleAtiva === pele.id && <Check size={13}/>}
                </button>
              ))}
            </div>

            <div className="aparencia-cores-livres" aria-label="Seletores livres de cor">
              <label>
                <span>FUNDO</span>
                <input type="color" value={configuracao.fundo} onChange={(evento) => atualizar({ fundo: evento.target.value.toUpperCase() })}/>
                <code>{configuracao.fundo}</code>
              </label>
              <label>
                <span>DESTAQUE</span>
                <input type="color" value={configuracao.destaque} onChange={(evento) => atualizar({ destaque: evento.target.value.toUpperCase() })}/>
                <code>{configuracao.destaque}</code>
              </label>
              <label>
                <span>SEGUNDO FIO</span>
                <input type="color" value={configuracao.segundoFio} onChange={(evento) => atualizar({ segundoFio: evento.target.value.toUpperCase() })}/>
                <code>{configuracao.segundoFio}</code>
              </label>
            </div>
          </section>

          <section className="aparencia-coluna-direita">
            <div className="aparencia-bloco aparencia-padroes">
              <div className="aparencia-titulo-bloco">
                <span>02</span>
                <div><h2>PADRÃO DE FUNDO</h2><p>Linha geométrica ou tecido em células.</p></div>
              </div>
              <div className="aparencia-grade-padroes">
                {PADROES_APARENCIA.map((padrao) => (
                  <button
                    type="button"
                    key={padrao.id}
                    className={configuracao.padrao === padrao.id ? 'ativa' : ''}
                    onClick={() => atualizar({ padrao: padrao.id })}
                    aria-pressed={configuracao.padrao === padrao.id}
                  >
                    <span className={`padrao-amostra padrao-${padrao.id}`}/>
                    <strong>{padrao.nome}</strong>
                  </button>
                ))}
              </div>
            </div>

            <div className="aparencia-bloco aparencia-disposicao">
              <div className="aparencia-titulo-bloco compacto"><span>03</span><div><h2>ONDE MORA</h2></div></div>
              <div className="aparencia-segmentos">
                {POSICOES_PADRAO.map((posicao) => (
                  <button type="button" key={posicao.id} className={configuracao.posicao === posicao.id ? 'ativa' : ''} onClick={() => atualizar({ posicao: posicao.id })} aria-pressed={configuracao.posicao === posicao.id}>{posicao.nome}</button>
                ))}
              </div>
              <div className="aparencia-titulo-bloco compacto forca"><span>04</span><div><h2>FORÇA</h2></div></div>
              <div className="aparencia-segmentos tres">
                {FORCAS_PADRAO.map((forca) => (
                  <button type="button" key={forca.id} className={configuracao.forca === forca.id ? 'ativa' : ''} onClick={() => atualizar({ forca: forca.id })} aria-pressed={configuracao.forca === forca.id}>{forca.nome}</button>
                ))}
              </div>
              <div className="aparencia-interface">
                <div className="aparencia-titulo-bloco compacto"><span>05</span><div><h2>INTERFACE NOVA</h2></div></div>
                <button
                  type="button"
                  role="switch"
                  className={`aparencia-interface-switch ${configuracao.interfaceNova ? 'ativa' : ''}`}
                  aria-checked={configuracao.interfaceNova}
                  onClick={() => atualizar({ interfaceNova: !configuracao.interfaceNova })}
                >
                  <span><strong>{configuracao.interfaceNova ? 'LIGADA' : 'DESLIGADA'}</strong><small>Troca somente o miolo do HOME.</small></span>
                  <i aria-hidden="true"><b/></i>
                </button>
              </div>
            </div>

            <div className={`aparencia-previa posicao-${configuracao.posicao}`} aria-label="Prévia ao vivo">
              <div className={`aparencia-preview-trama padrao-amostra padrao-${configuracao.padrao}`}/>
              <header><span>PRÉVIA AO VIVO</span><i>LOCAL</i></header>
              <div className="aparencia-previa-conversa">
                <small>O QUE FOI FALADO</small>
                <p>“ZARA, deixa a sala mais confortável.”</p>
                <small>EXEMPLO · O QUE A MÁQUINA FEZ</small>
                <code>LUZ NOTURNA · AJUSTE CONFIRMADO</code>
              </div>
              <footer>
                <span className="aparencia-confirmado"><i/> EXEMPLO · AÇÃO VERIFICADA</span>
                <span className="aparencia-nao-verificado">integrações externas · não verificado</span>
              </footer>
            </div>
          </section>
        </div>

        <footer className="aparencia-rodape">
          <div className={`aparencia-persistencia ${persistencia.tipo}`} aria-live="polite">
            {persistencia.tipo === 'verificado' && <Check size={14}/>}<span>{persistencia.texto}</span>
          </div>
          <button type="button" className="aparencia-restaurar" onClick={restaurar}><RotateCcw size={15}/> VOLTAR AO ORIGINAL</button>
          <button type="button" className="aparencia-guardar" onClick={guardar}><Save size={15}/> GUARDAR</button>
        </footer>
      </section>
    </div>
  );
};
