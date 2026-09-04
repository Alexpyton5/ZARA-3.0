import { useClock } from './useClock';

interface HeaderProps {
  userFirstName: string;
}

/**
 * Apenas a saudação (título + subtítulo) — sem data abaixo, igual ao MASTER
 * (a data vive no bloco do relógio, no canto superior direito).
 *
 * Saudação usa a hora real do sistema (useClock) em vez do "Boa tarde" fixo
 * que aparecia de manhã ou de madrugada igual.
 */
export function Header({ userFirstName }: HeaderProps) {
  const { greeting } = useClock();
  return (
    <header className="zh-header">
      <h1>{greeting}, {userFirstName}.</h1>
      <p>Produtividade com inteligência.</p>
    </header>
  );
}
