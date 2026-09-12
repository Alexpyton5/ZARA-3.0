import { useEffect, useRef, useState } from 'react';
import type { PowerPlan, PowerPlansData } from './types';
import { errorMessage } from './homeActions';

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
  const [error, setError] = useState('');
  const operation = useRef(false);
  const mounted = useRef(true);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

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
    if (!execute || operation.current) return;
    operation.current = true;
    setError('');
    setPending(true);
    execute('os_power_plan_set', { name: guid })
      .then(response => {
        if (!response?.success || !response.result?.success) throw new Error(response?.error || response?.result?.error || 'A alteração do plano não foi confirmada.');
      })
      .catch(cause => {
        if (mounted.current) setError(errorMessage(cause, 'Não foi possível alterar o plano de energia.'));
      })
      .finally(() => {
        operation.current = false;
        if (!mounted.current) return;
        setPending(false);
        setRefreshToken((token) => token + 1);
      });
  }

  return { supported, plans, pending, error, setPlan };
}
