import { useEffect, useRef, useState } from 'react';
import { errorMessage } from './homeActions';

export function useHomeFeedback() {
  const [feedback, setFeedback] = useState('');
  const [pending, setPending] = useState(false);
  const mounted = useRef(true);
  const running = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; clearTimeout(timer.current); };
  }, []);

  async function run(task: () => Promise<unknown> | undefined, successText = 'Solicitação concluída.') {
    if (running.current) return;
    running.current = true;
    clearTimeout(timer.current);
    setPending(true);
    setFeedback('');
    try {
      const response = await task() as { success?: boolean; error?: string; output?: string } | undefined;
      if (!response || response.success === false) throw new Error(response?.error || 'Este serviço não está conectado.');
      if (mounted.current) setFeedback(response.output || successText);
    } catch (cause) {
      if (mounted.current) setFeedback(errorMessage(cause));
    } finally {
      running.current = false;
      if (mounted.current) {
        setPending(false);
        timer.current = setTimeout(() => setFeedback(''), 7000);
      }
    }
  }
  return { feedback, pending, run };
}
