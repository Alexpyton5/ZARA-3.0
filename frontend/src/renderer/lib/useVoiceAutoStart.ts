import { useEffect, useRef } from 'react';

/** One attempt per signed-in session; manual stop and failures stay stopped. */
export function useVoiceAutoStart(
  sessionReady: boolean,
  conversationVisible: boolean,
  state: string,
  start: () => void | Promise<void>,
) {
  const attempted = useRef(false);
  useEffect(() => {
    if (!sessionReady) { attempted.current = false; return; }
    if (!conversationVisible || attempted.current) return;
    attempted.current = true;
    if (state === 'off') void start();
  }, [sessionReady, conversationVisible, state, start]);
}
