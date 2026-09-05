import React, { useEffect, useRef, useState } from 'react';
import { ZaraInterface } from './interface/ZaraInterface';
import { aplicarAparencia, useAparencia, PainelConfiguracoes } from './PainelConfiguracoes';

export const ZaraControlCenter: React.FC = () => {
  const raizRef = useRef<HTMLDivElement>(null);
  const [theme] = useState<'light' | 'dark'>('dark');
  const [configAberta, setConfigAberta] = useState(false);

  const {
    aparencia,
    setAparencia,
    desfazer,
    refazer,
    temPassado,
    temFuturo,
  } = useAparencia();

  // Apply appearance to root element whenever it changes
  useEffect(() => {
    aplicarAparencia(raizRef.current, aparencia);
  }, [aparencia]);

  const handleSettingsClick = () => {
    setConfigAberta(true);
  };

  return (
    <main
      ref={raizRef}
      className={`zara-preview theme-${theme} min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-700`}
    >
      <ZaraInterface onSettingsClick={handleSettingsClick} />
      <PainelConfiguracoes
        aberto={configAberta}
        onFechar={() => setConfigAberta(false)}
        aparencia={aparencia}
        onMudar={setAparencia}
        onDesfazer={desfazer}
        onRefazer={refazer}
        temPassado={temPassado}
        temFuturo={temFuturo}
      />
    </main>
  );
};