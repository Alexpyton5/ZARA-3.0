
import {
  House, MessageCircle, Folder, File, LayoutGrid, Workflow,
  BrainCircuit, FlaskConical, Monitor, Cpu, Settings,
} from 'lucide-react';
import profileAndroid from '../../../assets/zara-home/profile-android.png';
import zaraLogo from '../../../assets/zara-home/zara-mark.svg';

// Itens 1:1 com o MASTER (ordem exata, incluindo "Dispositivos").
const NAV_ITEMS: Array<{ label: string; Icon: typeof House }> = [
  { label: 'Hoje', Icon: House },
  { label: 'Conversas', Icon: MessageCircle },
  { label: 'Projetos', Icon: Folder },
  { label: 'Arquivos', Icon: File },
  { label: 'Aplicativos', Icon: LayoutGrid },
  { label: 'Automações', Icon: Workflow },
  { label: 'Memórias', Icon: BrainCircuit },
  { label: 'ZARA Lab', Icon: FlaskConical },
  { label: 'Dispositivos', Icon: Monitor },
  { label: 'Sistema', Icon: Cpu },
  { label: 'Configurações', Icon: Settings },
];

interface SidebarProps {
  active: string;
  onSelect: (item: string) => void;
  userName: string;
  userPhotoUrl?: string | null;
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
            type="button"
            aria-current={label === active ? 'page' : undefined}
            onClick={() => onSelect(label)}
          >
            <Icon size={17} strokeWidth={1.6} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="zh-user-card" type="button" onClick={() => onSelect('Configurações')} aria-label={`Configurações de ${userName}`}>
        <span className="zh-avatar">
          <img src={userPhotoUrl || profileAndroid} alt={userPhotoUrl ? `Foto de ${userName}` : "Avatar ZARA"} />
        </span>
        <span className="zh-user-meta">
          <strong>{userName}</strong>
          <small>Administrador</small>
        </span>
      </button>
    </aside>
  );
}
