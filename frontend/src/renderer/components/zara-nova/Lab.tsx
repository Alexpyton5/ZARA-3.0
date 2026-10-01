import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { Building2, LayoutGrid, Maximize2, Minimize2, Minus, Plus, RotateCcw, X } from 'lucide-react';
import type { AvatarInfo, MembroEquipe, ProjetoUsuario } from './types';
import { Equipe } from './Equipe';
import { avatarOriginal } from './avatares';
import officeImage from '../../assets/prototipo/core-office.webp';
import type { PilotProvider } from '../../lib/pilotConversation';

interface LabProps {
  projetos: ProjetoUsuario[];
  modo: 'equipe' | 'escritorio';
  onMudarModo: (modo: 'equipe' | 'escritorio') => void;
  provider?: PilotProvider;
  onNovoProjeto?: () => void;
}

// Coordenadas do app.js original, relativas ao core-office.webp inteiro.
// São locais na ilustração, não evidência de uma sala/computador provisionado.
const POSICOES: Readonly<Record<string, readonly [number, number]>> = {
  lyra: [18, 26], levi: [38, 29], azul: [60, 34],
  kai: [85, 40], noa: [34, 69], nix: [56, 78],
};
const ZOOM_MIN = 0.7;
const ZOOM_MAX = 1.75;
const ZOOM_PASSO = 0.15;

interface VinculoProjeto {
  projetoId: string;
  projeto: string;
  membro: MembroEquipe;
}
interface MembroComProjetos {
  avatar: AvatarInfo;
  vinculos: VinculoProjeto[];
}

const STATUS_LABEL: Record<MembroEquipe['status'], string> = {
  trabalhando: 'Trabalhando', pausado: 'Pausado', disponivel: 'Disponível',
};

function statusConhecido(valor: unknown): MembroEquipe['status'] | null {
  return valor === 'trabalhando' || valor === 'pausado' || valor === 'disponivel' ? valor : null;
}

function statusDoMembro(membro: MembroComProjetos): MembroEquipe['status'] | null {
  const estados = membro.vinculos.map((v) => statusConhecido(v.membro.status));
  return estados.length && estados.every((estado) => estado === estados[0]) ? estados[0] : null;
}

function Status({ valor }: { valor: MembroEquipe['status'] | null }) {
  return (
    <span className="nova-office-status" data-status={valor ?? 'desconhecido'}>
      <i aria-hidden="true" />
      {valor ? STATUS_LABEL[valor] : 'Estado não confirmado'}
    </span>
  );
}

function AvatarRosto({ avatar, tamanho = 44 }: { avatar: AvatarInfo; tamanho?: number }) {
  const src = avatarOriginal(avatar.id) ?? avatar.imagemUrl;
  const [falhou, setFalhou] = useState(false);
  useEffect(() => setFalhou(false), [src]);
  const iniciais = avatar.nome.trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '·';
  return (
    <span className={`avatar${!src || falhou ? ' pending-avatar' : ''}`} style={{ width: tamanho, height: tamanho }} aria-hidden="true">
      {src && !falhou ? <img src={src} alt="" loading="lazy" onError={() => setFalhou(true)} /> : iniciais}
    </span>
  );
}

function VistaOffice({ projetos }: { projetos: ProjetoUsuario[] }) {
  const [zoom, setZoom] = useState(1);
  const [imgFalhou, setImgFalhou] = useState(false);
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null);
  const [telaCheia, setTelaCheia] = useState(false);
  const [erroTelaCheia, setErroTelaCheia] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const fecharRef = useRef<HTMLButtonElement>(null);
  const origemRef = useRef<HTMLButtonElement | null>(null);
  const detalheId = useId();
  const podeTelaCheia = typeof document !== 'undefined' && document.fullscreenEnabled
    && typeof document.documentElement.requestFullscreen === 'function';

  const membros = useMemo<MembroComProjetos[]>(() => {
    const porId = new Map<string, MembroComProjetos>();
    for (const projeto of projetos) {
      for (const membro of projeto.membros) {
        const existente = porId.get(membro.avatar.id);
        const vinculo = { projetoId: projeto.id, projeto: projeto.nome, membro };
        if (existente) existente.vinculos.push(vinculo);
        else porId.set(membro.avatar.id, { avatar: membro.avatar, vinculos: [vinculo] });
      }
    }
    return Array.from(porId.values());
  }, [projetos]);
  const selecionado = membros.find((m) => m.avatar.id === selecionadoId) ?? null;

  const fecharDetalhe = () => {
    setSelecionadoId(null);
    if (origemRef.current?.isConnected) origemRef.current.focus({ preventScroll: true });
  };

  useEffect(() => {
    if (selecionadoId) fecharRef.current?.focus({ preventScroll: true });
  }, [selecionadoId]);

  useEffect(() => {
    if (selecionadoId && !selecionado) setSelecionadoId(null);
  }, [selecionadoId, selecionado]);

  useEffect(() => {
    if (!selecionadoId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setSelecionadoId(null);
      if (origemRef.current?.isConnected) origemRef.current.focus({ preventScroll: true });
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selecionadoId]);

  useEffect(() => {
    const root = rootRef.current;
    const onFullscreen = () => setTelaCheia(document.fullscreenElement === root);
    document.addEventListener('fullscreenchange', onFullscreen);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreen);
      if (root && document.fullscreenElement === root) void document.exitFullscreen().catch(() => {});
    };
  }, []);

  const ajustarZoom = (valor: number) => {
    setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number(valor.toFixed(2)))));
  };
  const alternarTelaCheia = async () => {
    setErroTelaCheia('');
    try {
      if (document.fullscreenElement === rootRef.current) await document.exitFullscreen();
      else if (rootRef.current && podeTelaCheia) await rootRef.current.requestFullscreen();
    } catch {
      setErroTelaCheia('Não foi possível abrir a tela cheia. A vista continua disponível aqui.');
    }
  };
  const selecionar = (id: string, origem: HTMLButtonElement) => {
    if (selecionadoId === id) { fecharDetalhe(); return; }
    origemRef.current = origem;
    setSelecionadoId(id);
  };
  const posicaoPara = (id: string) => {
    const key = id.trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(POSICOES, key) ? POSICOES[key] : undefined;
  };

  return (
    <div ref={rootRef} className={`office-space nova-office${selecionado ? ' has-detail' : ''}`}>
      <div className="office-toolbar">
        <div className="office-title">
          <strong>Escritório</strong>
          <span>Escritório ilustrado · membros dos seus projetos</span>
        </div>
        <div className="zoom-controls" role="group" aria-label="Controles da vista">
          <button className="icon-button" type="button" aria-label="Diminuir zoom" title="Diminuir zoom" disabled={zoom <= ZOOM_MIN || imgFalhou} onClick={() => ajustarZoom(zoom - ZOOM_PASSO)}>
            <Minus size={18} aria-hidden="true" />
          </button>
          <span className="zoom-number" aria-live="polite" aria-atomic="true">{Math.round(zoom * 100)}%</span>
          <button className="icon-button" type="button" aria-label="Aumentar zoom" title="Aumentar zoom" disabled={zoom >= ZOOM_MAX || imgFalhou} onClick={() => ajustarZoom(zoom + ZOOM_PASSO)}>
            <Plus size={18} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" aria-label="Restaurar vista" title="Restaurar vista" disabled={zoom === 1 || imgFalhou} onClick={() => ajustarZoom(1)}>
            <RotateCcw size={18} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" aria-label={telaCheia ? 'Sair da tela cheia' : 'Ver escritório em tela cheia'} title={podeTelaCheia ? (telaCheia ? 'Sair da tela cheia' : 'Tela cheia') : 'Tela cheia indisponível neste ambiente'} aria-pressed={telaCheia} disabled={!podeTelaCheia} onClick={() => void alternarTelaCheia()}>
            {telaCheia ? <Minimize2 size={18} aria-hidden="true" /> : <Maximize2 size={18} aria-hidden="true" />}
          </button>
        </div>
      </div>
      {erroTelaCheia && <p className="nova-office-notice" role="status">{erroTelaCheia}</p>}

      <div className="nova-office-body">
        <aside className="nova-office-sidebar" aria-label="Membros dos projetos">
          <div className="nova-office-heading">
            <h2>Nos seus projetos</h2>
            <span className="room-count" aria-label={`${membros.length} membros`}>{membros.length}</span>
          </div>
          {membros.length ? (
            <ul className="nova-office-members">
              {membros.map((m) => (
                <li key={m.avatar.id}>
                  <button type="button" className={`nova-office-member${m.avatar.id === selecionadoId ? ' selected' : ''}`} aria-pressed={m.avatar.id === selecionadoId} aria-controls={selecionado ? detalheId : undefined} onClick={(e) => selecionar(m.avatar.id, e.currentTarget)}>
                    <AvatarRosto avatar={m.avatar} tamanho={40} />
                    <span className="nova-office-member-copy">
                      <strong>{m.avatar.nome}</strong>
                      <small>{m.avatar.papel || 'Especialidade não informada'}</small>
                      <Status valor={statusDoMembro(m)} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="nova-office-empty" role="status">
              <Building2 size={28} aria-hidden="true" />
              <strong>{projetos.length ? 'Nenhum membro recebido' : 'Nenhum projeto recebido'}</strong>
              <p>A equipe aparece aqui quando os seus projetos tiverem membros.</p>
            </div>
          )}
          <p className="nova-office-sidebar-note">Os estados são os informados pelos projetos.</p>
        </aside>

        <div className="nova-office-view">
          <div className="office-canvas" tabIndex={0} role="region" aria-label="Vista ilustrada do escritório. Ao ampliar, use a rolagem ou as setas para explorar.">
            {imgFalhou ? (
              <div className="nova-office-empty nova-office-image-error" role="status">
                <strong>A ilustração não carregou</strong>
                <p>Os membros e seus detalhes continuam disponíveis na lista.</p>
              </div>
            ) : (
              <div className="nova-office-stage" style={{ '--office-zoom': zoom } as CSSProperties}>
                <div className="office-scene">
                  <img className="office-original" src={officeImage} width={1586} height={992} alt="Ilustração isométrica original: seis avatares nas mesas, estúdio de interface e sala de reuniões." draggable={false} onError={() => setImgFalhou(true)} />
                  {membros.map((m) => {
                    const posicao = posicaoPara(m.avatar.id);
                    if (!posicao) return null;
                    const ativo = selecionadoId === m.avatar.id;
                    const status = statusDoMembro(m);
                    return (
                      <button key={m.avatar.id} type="button" className={`room-pin${ativo ? ' selected' : ''}`} style={{ left: `${posicao[0]}%`, top: `${posicao[1]}%` }} aria-label={`Ver ${m.avatar.nome} — ${status ? STATUS_LABEL[status] : 'Estado não confirmado'}`} aria-pressed={ativo} aria-controls={selecionado ? detalheId : undefined} onClick={(e) => selecionar(m.avatar.id, e.currentTarget)}>
                        <AvatarRosto avatar={m.avatar} tamanho={30} />
                        <span className="nova-office-pin-status" data-status={status ?? 'desconhecido'} aria-hidden="true" />
                        <span className="pin-name">{m.avatar.nome}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
          <div className="office-caption">
            <span>Ilustração de referência. Os marcadores mostram os membros recebidos.</span>
            <span>Sem sala identificada? Selecione o membro na lista.</span>
          </div>
        </div>

        {selecionado && (
          <aside id={detalheId} className="room-detail" aria-label={`Detalhes de ${selecionado.avatar.nome}`}>
            <button ref={fecharRef} className="icon-button detail-close" type="button" aria-label="Fechar detalhes" title="Fechar detalhes" onClick={fecharDetalhe}>
              <X size={18} aria-hidden="true" />
            </button>
            <div className="detail-portrait"><AvatarRosto avatar={selecionado.avatar} tamanho={88} /></div>
            <h2>{selecionado.avatar.nome}</h2>
            <p className="detail-role">{selecionado.avatar.papel || 'Especialidade não informada'}</p>
            <p className="detail-description">{posicaoPara(selecionado.avatar.id) ? 'Local identificado na ilustração original.' : 'Este membro ainda não tem sala identificada nesta ilustração.'}</p>
            <ul className="nova-office-assignments">
              {selecionado.vinculos.map((v, i) => (
                <li key={`${v.projetoId}-${i}`}>
                  <strong>{v.projeto}</strong>
                  <Status valor={statusConhecido(v.membro.status)} />
                  <p>{v.membro.tarefaAtual || 'Nenhuma tarefa informada neste projeto.'}</p>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>
    </div>
  );
}

/** O escritório é uma vista opcional; a equipe mantém a organização por projetos. */
export function Lab({ projetos, modo, onMudarModo, provider = 'muse', onNovoProjeto }: LabProps) {
  if (provider === 'openai') return <section className="nova-lab" aria-label="Espaço da equipe OpenAI">
    <div className="confidence-card"><h2>Seu espaço de trabalho</h2><p>Seu piloto OpenAI na conversa e os projetos reais do motor em um só lugar.</p></div>
    <Equipe projetos={projetos} onNovoProjeto={onNovoProjeto} />
  </section>;
  return (
    <section className="nova-lab" aria-label="Lab">
      <div className="segmented nova-lab-modes" role="group" aria-label="Visão do Lab">
        <button type="button" className={modo === 'equipe' ? 'active' : ''} aria-pressed={modo === 'equipe'} onClick={() => onMudarModo('equipe')}>
          <LayoutGrid size={16} aria-hidden="true" />Equipe
        </button>
        <button type="button" className={modo === 'escritorio' ? 'active' : ''} aria-pressed={modo === 'escritorio'} onClick={() => onMudarModo('escritorio')}>
          <Building2 size={16} aria-hidden="true" />Escritório
        </button>
      </div>
      {modo === 'equipe' ? <Equipe projetos={projetos} onNovoProjeto={onNovoProjeto} /> : <VistaOffice projetos={projetos} />}
    </section>
  );
}

export default Lab;
