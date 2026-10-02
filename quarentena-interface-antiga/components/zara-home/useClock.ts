import { useEffect, useState } from 'react';

const POLL_MS = 15000;

export interface ClockData {
  time: string;
  date: string;
  greeting: 'Bom dia' | 'Boa tarde' | 'Boa noite';
}

const DIAS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
const MESES = [
  'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
  'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
];

function build(): ClockData {
  const now = new Date();
  const hours = now.getHours();
  const time = `${String(hours).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const date = `${DIAS[now.getDay()]} · ${now.getDate()} ${MESES[now.getMonth()]}`;
  const greeting = hours < 12 ? 'Bom dia' : hours < 18 ? 'Boa tarde' : 'Boa noite';
  return { time, date, greeting };
}

/**
 * Relógio e saudação real do sistema local — substitui os textos fixos
 * "15:30"/"Dom · 19 Mai"/"Boa tarde" que a Home mostrava sempre, não importa
 * a hora real. Sem dependência de IPC/backend: só `new Date()` do renderer.
 */
export function useClock(): ClockData {
  const [data, setData] = useState<ClockData>(build);

  useEffect(() => {
    const interval = setInterval(() => setData(build()), POLL_MS);
    return () => clearInterval(interval);
  }, []);

  return data;
}
