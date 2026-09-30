import { useEffect, useMemo, useState } from 'react';
import { Building2, LayoutGrid, Minus, Plus, RotateCcw, X } from 'lucide-react';
import type { AvatarInfo, MembroEquipe, ProjetoUsuario } from './types';
import { Equipe } from './Equipe';

interface LabProps {
  projetos: ProjetoUsuario[];
  modo: 'equipe' | 'escritorio';
  onMudarModo: (modo: 'equipe' | 'escritorio') => void;
}

/** Ilustração original THE OFFICE do molde (o .png caiu — o site devolve HTML nele). */
const OFFICE_IMG = 'https://zara-ui-lab.zoeeproject.chatgpt.site/assets/core-office.webp';

/** Posições dos marcadores sobre a ilustração (distribuição visual, sem significado real). */
const POSICOES: Array<[number, number]> = [
  [13, 57], [18, 26], [34, 69], [38, 29], [60, 34], [85, 40], [56, 78], [82, 79],
  [25, 45], [47, 55], [70, 62], [50, 38],
];

interface MembroComProjeto {
  membro: MembroEquipe;
  projeto: string;
}

function AvatarRosto({ avatar, tamanho = 44 }: { avatar: AvatarInfo; tamanho?: number }) {
  if (avatar.imagemUrl) {
    return (
      <span className="avatar" style={{ width: tamanho, height: tamanho }}>
        <img src={avatar.imagemUrl} alt={avatar.nome} loading="lazy" />
      </span>
    );
  }
  const iniciais = avatar.nome.trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '·';
  return (
    <span className="avatar pending-avatar" style={{ width: tamanho, height: tamanho }} aria-hidden="true">
      {iniciais}
    </span>
  );
}

const STATUS_LABEL: Record<MembroEquipe['status'], string> = {
  trabalhando: 'Trabalhando',
  pausado: 'Pausado',
  disponivel: 'Disponível',
};

/** Animação de cada marcador = o STATUS REAL do avatar (nada decorativo). */
function MarcadorStatus({ status }: { status: MembroEquipe['status'] }) {
  if (status === 'trabalhando') {
    return (
      <span className="theoffice-typing" aria-hidden="true" title="Digitando">
        <i /><i /><i />
      </span>
    );
  }
  if (status === 'pausado') {
    return (
      <span className="theoffice-think" aria-hidden="true" title="Pensando">
        …
      </span>
    );
  }
  return <span className="theoffice-glow" aria-hidden="true" title="Disponível" />;
}

function VistaOffice({ projetos }: { projetos: ProjetoUsuario[] }) {
  const [zoom, setZoom] = useState(1);
  const [imgFalhou, setImgFalhou] = useState(false);
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null);

  const membros = useMemo<MembroComProjeto[]>(() => {
    const vistos = new Set<string>();
    const lista: MembroComProjeto[] = [];
    for (const projeto of projetos) {
      for (const membro of projeto.membros) {
        if (vistos.has(membro.avatar.id)) continue;
        vistos.add(membro.avatar.id);
        lista.push({ membro, projeto: projeto.nome });
      }
    }
    return lista;
  }, [projetos]);

  const selecionado = membros.find((m) => m.membro.avatar.id === selecionadoId) || null;

  useEffect(() => {
    if (!selecionado) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelecionadoId(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selecionado]);

  const ajustarZoom = (valor: number) => setZoom(Math.min(1.75, Math.max(0.7, Number(valor.toFixed(2)))));

  return (
    <div className="office-space theoffice-alive">
      <style>{`
        .theoffice-pinwrap{position:absolute;z-index:2;transform:translate(-50%,-50%)}
        .theoffice-typing{position:absolute;left:50%;top:-22px;transform:translateX(-50%);display:flex;gap:3px;background:#f7f4e9ee;border:1px solid #ffffff88;border-radius:8px;padding:4px 6px;box-shadow:0 2px 7px #0002}
        .theoffice-typing i{width:5px;height:5px;border-radius:50%;background:#805a37;animation:theoffice-dot 1s ease-in-out infinite}
        .theoffice-typing i:nth-child(2){animation-delay:.15s}
        .theoffice-typing i:nth-child(3){animation-delay:.3s}
        @keyframes theoffice-dot{0%,100%{transform:translateY(0);opacity:.55}50%{transform:translateY(-4px);opacity:1}}
        .theoffice-think{position:absolute;left:50%;top:-24px;transform:translateX(-50%);background:#f7f4e9ee;border:1px solid #ffffff88;border-radius:8px;padding:2px 8px;font-size:13px;color:#805a37;box-shadow:0 2px 7px #0002;animation:theoffice-float 3s ease-in-out infinite}
        @keyframes theoffice-float{0%,100%{transform:translate(-50%,0)}50%{transform:translate(-50%,-7px)}}
        .theoffice-glow{position:absolute;inset:-5px;border-radius:50%;border:2px solid var(--mint);opacity:.7;animation:theoffice-breathe 3.2s ease-in-out infinite;pointer-events:none}
        @keyframes theoffice-breathe{0%,100%{transform:scale(1);opacity:.35}50%{transform:scale(1.18);opacity:.8}}
        .theoffice-fallback{min-height:300px;border-radius:16px;background:linear-gradient(135deg,#f6efe2 0%,#efe3cc 45%,#e5d3b3 100%);display:flex;align-items:center;justify-content:center;text-align:center;padding:24px}
        .theoffice-fallback p{max-width:460px;color:#6b4f2f;font-size:14px;line-height:1.6}
        .theoffice-fallback strong{display:block;font-size:15px;margin-bottom:4px}
        .theoffice-legend{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:12px;color:#e8ecd9}
        .theoffice-legend b{font-weight:600}
        @media (prefers-reduced-motion: reduce){
          .theoffice-alive *,.theoffice-alive *::before,.theoffice-alive *::after{animation:none!important}
        }
      `}</style>

      <div className="office-toolbar">
        <div className="office-title">
          <strong>THE OFFICE</strong>
          <span>O escritório da equipe — cada avatar com sua sala e seu computador</span>
        </div>
        <div className="zoom-controls" aria-label="Controles da vista">
          <button className="icon-button" type="button" aria-label="Diminuir zoom" onClick={() => ajustarZoom(zoom - 0.15)}>
            <Minus size={15} aria-hidden="true" />
          </button>
          <span className="zoom-number" aria-live="polite">{Math.round(zoom * 100)}%</span>
          <button className="icon-button" type="button" aria-label="Aumentar zoom" onClick={() => ajustarZoom(zoom + 0.15)}>
            <Plus size={15} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" aria-label="Restaurar vista" onClick={() => ajustarZoom(1)}>
            <RotateCcw size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="office-canvas">
        <div className="office-scene" style={{ transform: `scale(${zoom})` }}>
          {imgFalhou ? (
            <div className="theoffice-fallback" role="status">
              <p>
                <strong>Referência visual pendente</strong>
                A ilustração do escritório não carregou — os marcadores da equipe continuam ativos sobre esta vista.
              </p>
            </div>
          ) : (
            <img
              className="office-original"
              src={OFFICE_IMG}
              alt="Ilustração do escritório da equipe"
              draggable={false}
              onError={() => setImgFalhou(true)}
            />
          )}
          {membros.map(({ membro }, i) => {
            const [x, y] = POSICOES[i % POSICOES.length] ?? [50, 50];
            const ativo = selecionadoId === membro.avatar.id;
            return (
              <span key={membro.avatar.id} className="theoffice-pinwrap" style={{ left: `${x}%`, top: `${y}%` }}>
                <MarcadorStatus status={membro.status} />
                <button
                  type="button"
                  className={`room-pin${ativo ? ' selected theoffice-pin-active' : ''}`}
                  style={{ position: 'relative' }}
                  aria-label={`Ver ${membro.avatar.nome}, ${membro.avatar.papel} — ${STATUS_LABEL[membro.status]}`}
                  aria-pressed={ativo}
                  onClick={() => setSelecionadoId(ativo ? null : membro.avatar.id)}
                >
                  <AvatarRosto avatar={membro.avatar} tamanho={29} />
                  <span className="pin-name">{membro.avatar.nome}</span>
                </button>
              </span>
            );
          })}
        </div>
      </div>

      <div className="office-caption">
        <span className="hint">Toque em um marcador para ver o avatar</span>
        <span className="theoffice-legend" aria-label="Legenda dos movimentos">
          <span><b>···</b> digitando = trabalhando</span>
          <span><b>…</b> flutuando = pausado</span>
          <span><b>○</b> brilho = disponível</span>
        </span>
      </div>

      {selecionado && (
        <aside className="room-detail" aria-label={`Detalhe de ${selecionado.membro.avatar.nome}`}>
          <button className="icon-button detail-close" type="button" aria-label="Fechar detalhe" onClick={() => setSelecionadoId(null)}>
            <X size={17} aria-hidden="true" />
          </button>
          <div className="detail-portrait" style={{ display: 'grid', placeItems: 'center', padding: 12 }}>
            <AvatarRosto avatar={selecionado.membro.avatar} tamanho={84} />
          </div>
          <h2>{selecionado.membro.avatar.nome}</h2>
          <p className="detail-role">{selecionado.membro.avatar.papel}</p>
          <p className="detail-description">
            Bot customizável — com sua sala, seu computador e sua especialidade.
          </p>
          <div className="detail-meta">
            <span>{selecionado.projeto}</span>
            <strong>{STATUS_LABEL[selecionado.membro.status]}</strong>
          </div>
          {selecionado.membro.tarefaAtual && (
            <p className="detail-description">{selecionado.membro.tarefaAtual}</p>
          )}
        </aside>
      )}
    </div>
  );
}

/**
 * Lab — ADENDO #2: o escritório (THE OFFICE) é UMA OPÇÃO, não a experiência inteira.
 * Visão padrão = equipe (reaproveita o grid da Equipe);
 * "Ver THE OFFICE" mostra a vista redesenhada do escritório, viva conforme o status real.
 */
export function Lab({ projetos, modo, onMudarModo }: LabProps) {
  return (
    <section aria-label="Lab">
      <div
        className="segmented"
        role="group"
        aria-label="Visão do Lab"
        style={{ marginBottom: 18, width: 'fit-content' }}
      >
        <button
          type="button"
          className={modo === 'equipe' ? 'active' : ''}
          aria-pressed={modo === 'equipe'}
          onClick={() => onMudarModo('equipe')}
        >
          <LayoutGrid size={16} aria-hidden="true" />
          {modo === 'equipe' ? 'Equipe' : 'Ver como equipe'}
        </button>
        <button
          type="button"
          className={modo === 'escritorio' ? 'active' : ''}
          aria-pressed={modo === 'escritorio'}
          onClick={() => onMudarModo('escritorio')}
        >
          <Building2 size={16} aria-hidden="true" />
          {modo === 'escritorio' ? 'THE OFFICE' : 'Ver THE OFFICE'}
        </button>
      </div>

      {modo === 'equipe' ? (
        <Equipe projetos={projetos} />
      ) : (
        <VistaOffice projetos={projetos} />
      )}
    </section>
  );
}

export default Lab;
