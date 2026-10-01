import { useEffect, useRef } from 'react';

export type VoiceStartRequest = { provider: string; page: string };
type VoiceStartOptions = {
  provider: string;
  page: string;
  ready: boolean;
  accountOpen: boolean;
  request?: VoiceStartRequest | null;
  consume?: (fulfilled: boolean) => void;
};

/** Login can defer an explicit click; one consumer prevents a double toggle. */
export function useVoiceAutoStart(
  sessionReady: boolean,
  conversationVisible: boolean,
  state: string,
  start: () => void | Promise<void>,
  options?: VoiceStartOptions,
) {
  const attempted = useRef(false);
  const previousProvider = useRef(options?.provider);
  const consumed = useRef<VoiceStartRequest | null>(null);
  useEffect(() => {
    if (previousProvider.current !== options?.provider) {
      attempted.current = false;
    }
    previousProvider.current = options?.provider;
    const request = options?.request;
    if (request) {
      if (consumed.current === request) return;
      if (request.provider !== options.provider || request.page !== options.page || !options.accountOpen) {
        consumed.current = request; attempted.current = true;
        options.consume?.(false);
        return;
      }
      if (!options.ready) return;
      consumed.current = request; attempted.current = true;
      options.consume?.(true);
      if (state === 'off' || state === 'error') void start();
      return;
    }
    if (options?.accountOpen) {
      // Inspecting an account must not open the mic behind it or upon return.
      attempted.current = true;
      return;
    }
    // Editable-page readiness can flicker during navigation; it is not a login ID.
    if (!sessionReady) return;
    if (!conversationVisible || attempted.current) return;
    attempted.current = true;
    if (state === 'off') void start();
  }, [sessionReady, conversationVisible, state, start, options]);
  return () => { attempted.current = true; };
}
