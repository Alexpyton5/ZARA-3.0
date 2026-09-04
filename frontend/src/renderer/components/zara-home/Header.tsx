

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
      <h1>Boa tarde, {userFirstName}.</h1>
      <p>Produtividade com inteligência.</p>
    </header>
  );
}
