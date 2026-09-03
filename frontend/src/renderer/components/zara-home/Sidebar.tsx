
import {
  House, MessageCircle, Folder, File, LayoutGrid, Workflow,
  BrainCircuit, FlaskConical, Cpu, Settings,
} from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-mark.png';

// Itens 1:1 com o MASTER ("Início" em vez de "Hoje"; sem "Dispositivos").
const NAV_ITEMS: Array<{ label: string; Icon: typeof House }> = [
  { label: 'Início', Icon: House },
  { label: 'Conversas', Icon: MessageCircle },
  { label: 'Projetos', Icon: Folder },
  { label: 'Arquivos', Icon: File },
  { label: 'Aplicativos', Icon: LayoutGrid },
  { label: 'Automações', Icon: Workflow },
  { label: 'Memórias', Icon: BrainCircuit },
  { label: 'ZARA Lab', Icon: FlaskConical },
  { label: 'Sistema', Icon: Cpu },
  { label: 'Configurações', Icon: Settings },
];

interface SidebarProps {
  active: string;
  onSelect: (item: string) => void;
  userName: string;
  userPhotoUrl?: string | null;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

export function Sidebar({ active, onSelect, userName, userPhotoUrl }: SidebarProps) {
  return (
    <aside className="zh-sidebar" aria-label="Navegação principal">
      <div className="zh-sidebar-brand">
        <img src={zaraLogo} alt="Logo ZARA" />
        <span>ZARA</span>
      </div>
      <nav className="zh-nav">
        {NAV_ITEMS.map(({ label, Icon }) => (
          <button
            key={label}
            className="zh-nav-item"
            data-active={label === active}
            onClick={() => onSelect(label)}
          >
            <Icon size={17} strokeWidth={1.6} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="zh-user-card" type="button">
        <span className="zh-avatar">
          {userPhotoUrl ? <img src={userPhotoUrl} alt={`Foto de ${userName}`} /> : initials(userName)}
        </span>
        <span className="zh-user-meta">
          <strong>{userName}</strong>
          <small>Administrador</small>
        </span>
      </button>
    </aside>
  );
}
