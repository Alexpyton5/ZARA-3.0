/**
 * App — raiz da interface nova da ZARA (substitui a ZaraHome verde).
 *
 *   ThemeProvider (frente TEMA, modo controlado) — o visual acompanha o avatar ativo
 *     └─ portão de entrada: sem avatar escolhido → tela Entrada
 *     └─ com avatar → ZaraNovaShell (frente CORE) com navegação por NavKey
 *
 * INTEGRAÇÃO FINAL (FRENTE PORTÃO, 2026-09-30): os substitutos TODO(TEMA) e
 * TODO(CORE) foram removidos — este arquivo agora importa os módulos reais
 * entregues pelas frentes. Nada de código morto, nada de stub temporário.
 *
 * Dados das telas (honesto): a FIAÇÃO ainda não entregou os hooks de
 * trabalho/atividade/decisões — as telas recebem listas vazias e mostram os
 * estados vazios honestos que já trazem ("Nada em andamento agora" etc.).
 * A voz recebe `voz`/`onEnviar` indefinidos até o Codex decidir o caminho
 * (TODO em useVozReal.ts) — o rodapé e o botão explicam, nada é fingido.
 */

import { useState } from 'react';
import type { AvatarInfo, NavKey } from './components/zara-nova/types';
import { ThemeProvider, useAvatar } from './components/zara-nova/theme/ThemeContext';
import { ZaraNovaShell, useToast } from './components/zara-nova/chrome/ZaraNovaShell';
import { Entrada } from './components/zara-nova/Entrada';
import { Inicio } from './components/zara-nova/Inicio';
import { Conversa } from './components/zara-nova/Conversa';
import { Voz } from './components/zara-nova/Voz';
import { Atividade } from './components/zara-nova/Atividade';
import { Equipe } from './components/zara-nova/Equipe';
import { Lab } from './components/zara-nova/Lab';
import { BotaoOperarComputador, useSupercerebroStatus } from './lib/zaraNovaIpc';

/** Telas logadas: só montadas quando há avatar (portão de entrada). */
function TelasLogadas({ avatar }: { avatar: AvatarInfo }) {
  const toast = useToast();
  const [nav, setNav] = useState<NavKey>('inicio');
  const [modoLab, setModoLab] = useState<'equipe' | 'escritorio'>('equipe');
  const supercerebro = useSupercerebroStatus();

  return (
    <ZaraNovaShell active={nav} onNavigate={setNav}>
      {nav === 'inicio' && (
        <Inicio
          cuidando={{
            avatar,
            // TODO(CODEX): 'supercerebro-status' não tem handler no backend
            // (Manual §8.1) — até a decisão, unknown conta como "não confirmado".
            supervisionado: supercerebro.active && !supercerebro.unknown,
          }}
          emAndamento={[]}
          entregas={[]}
          decisoes={[]}
          onPausar={() =>
            toast('Pausar a equipe ainda não tem canal no backend — registrado para a etapa de fiação.')
          }
          onConversar={() => setNav('conversa')}
          onVerOffice={() => setNav('lab')}
        />
      )}
      {nav === 'conversa' && (
        <Conversa
          avatar={avatar}
          // TODO(CODEX): caminho de voz da tela nova indefinido
          // (ver useVozReal.ts) — voz/onEnviar ligam na decisão.
          voz={undefined}
          onEnviar={undefined}
          onAbrirVoz={() => setNav('voz')}
        />
      )}
      {nav === 'voz' && (
        <Voz
          state="ready"
          onMicClick={() =>
            toast('A voz de verdade conecta na etapa de fiação — a decisão do caminho está com o Codex.')
          }
        />
      )}
      {nav === 'atividade' && <Atividade itens={[]} />}
      {nav === 'equipe' && <Equipe projetos={[]} />}
      {nav === 'lab' && <Lab projetos={[]} modo={modoLab} onMudarModo={setModoLab} />}
    </ZaraNovaShell>
  );
}

function AppConteudo({ onEscolherAvatar }: { onEscolherAvatar: (a: AvatarInfo) => void }) {
  const { avatar } = useAvatar();

  if (avatar === null) {
    // Portão de entrada: escolher o avatar aqui aplica o tema na hora
    // (ThemeProvider em modo controlado espelha a prop `avatar` do App).
    return <Entrada onEscolherAvatar={onEscolherAvatar} onConcluir={() => undefined} />;
  }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
      <TelasLogadas avatar={avatar} />
      {/* Posto de comando do use-computer (Fase 4): entrada discreta e global. */}
      <div style={{ position: 'absolute', right: '18px', bottom: '18px' }}>
        <BotaoOperarComputador />
      </div>
    </div>
  );
}

function App() {
  const [avatar, setAvatar] = useState<AvatarInfo | null>(null);

  return (
    <ThemeProvider avatar={avatar}>
      <AppConteudo onEscolherAvatar={setAvatar} />
    </ThemeProvider>
  );
}



export default App;
