import { useEffect, useState } from 'react';
import type { PowerPlan, PowerPlansData } from './types';

/**
 * Usa `window.zaraIPC.action.execute('os_power_plan_list'|'os_power_plan_set', ...)`
 * — actions reais já registradas em `core/actions/system_advanced.py`
 * (powercfg.exe /LIST e /SETACTIVE, com reverificação depois de trocar).
 * Sem canal novo, sem estado inventado: sem resposta real, `plans` fica
 * vazio e o botão de energia mostra indisponível.
 *
 * `refreshToken` dispara um novo fetch dentro do efeito (mesmo padrão de
 * `useSystemMetrics`) em vez de chamar setState direto dentro do efeito via
 * uma função memoizada — evita o cascading render que o eslint acusa.
 */
export function usePowerPlans(): PowerPlansData {
  const [plans, setPlans] = useState<PowerPlan[]>([]);
  const [supported, setSupported] = useState(false);
  const [pending, setPending] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const execute = window.zaraIPC?.action?.execute;
    if (!execute) return;

    let cancelled = false;

    async function fetchPlans() {
      try {
        const response = await execute!('os_power_plan_list', {});
        if (cancelled) return;
        const result = response?.result;
        if (result?.success && Array.isArray(result?.data)) {
          setPlans(result.data);
          setSupported(true);
        } else {
          setPlans([]);
          setSupported(false);
        }
      } catch {
        if (!cancelled) {
          setPlans([]);
          setSupported(false);
        }
      }
    }

    fetchPlans();
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  function setPlan(guid: string) {
    const execute = window.zaraIPC?.action?.execute;
    if (!execute || pending) return;
    setPending(true);
    execute('os_power_plan_set', { name: guid })
      .catch(() => {
        // Falhou — o refresh a seguir mostra o estado real (o plano
        // anterior, não o que tentamos setar), sem fingir sucesso.
      })
      .finally(() => {
        setPending(false);
        setRefreshToken((token) => token + 1);
      });
  }

  return { supported, plans, pending, setPlan };
}
