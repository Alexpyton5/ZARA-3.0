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
 * Apenas a saudação (título + subtítulo) — sem data abaixo, igual ao MASTER
 * (a data vive no bloco do relógio, no canto superior direito).
 */
export function Header({ userFirstName }: HeaderProps) {
  return (
    <header className="zh-header">
      <h1>{greeting(new Date().getHours())}, {userFirstName}.</h1>
      <p>Produtividade com inteligência.</p>
    </header>
  );
}
