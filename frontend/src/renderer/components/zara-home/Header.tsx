import { useEffect, useState } from 'react';

function greeting(hour: number): string {
  if (hour < 6) return 'Boa madrugada';
  if (hour < 12) return 'Bom dia';
  if (hour < 18) return 'Boa tarde';
  return 'Boa noite';
}

interface HeaderProps {
  userFirstName: string;
}

/**
 * Apenas a saudação (título + subtítulo + data). O campo de comando vive
 * fora dela, centralizado na top bar — igual ao MASTER.
 */
export function Header({ userFirstName }: HeaderProps) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const date = now.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' });

  return (
    <header className="zh-header">
      <h1>{greeting(now.getHours())}, {userFirstName}.</h1>
      <p>Produtividade com inteligência.</p>
      <div className="zh-clock-row">
        <span>{date}</span>
      </div>
    </header>
  );
}
