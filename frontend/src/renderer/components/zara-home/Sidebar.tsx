
import zaraLogo from '../../../assets/zara-home/zara-logo.png';

const NAV_ITEMS = [
  'Hoje', 'Conversas', 'Projetos', 'Arquivos', 'Aplicativos', 'Automações',
  'Memórias', 'ZARA Lab', 'Dispositivos', 'Sistema', 'Configurações',
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
        {NAV_ITEMS.map((item) => (
          <button
            key={item}
            className="zh-nav-item"
            data-active={item === active}
            onClick={() => onSelect(item)}
          >
            {item}
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
