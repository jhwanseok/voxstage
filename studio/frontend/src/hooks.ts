import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, type Bot } from "./api";

/** Fetch on mount and whenever `deps` change; `reload` fetches again. `loading` is true until the first answer. */
export function useFetch<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let alive = true;
    setLoading(true);
    api.get<T>(path).then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(e); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading: loading && data === null, reload, setData };
}

/** Ask the browser to warn before leaving the page while `dirty`. */
export function useUnsavedWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);
}

export interface Shell {
  bots: Bot[];
  botsError: Error | null;
  botsLoading: boolean;
  /** Call after any change to content: bot status and validation badges are refetched. */
  refresh: () => void;
  version: number;
}
export const ShellContext = createContext<Shell>({ bots: [], botsError: null, botsLoading: false, refresh: () => {}, version: 0 });
export const useShell = () => useContext(ShellContext);
