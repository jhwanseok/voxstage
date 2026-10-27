import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, type Bot } from "./api";

/** Fetch on mount and whenever `deps` change; `reload` fetches again. */
export function useFetch<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let alive = true;
    api.get<T>(path).then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, reload, setData };
}

export interface Shell {
  bots: Bot[];
  /** Call after any change to content: bot status and validation badges are refetched. */
  refresh: () => void;
  version: number;
}
export const ShellContext = createContext<Shell>({ bots: [], refresh: () => {}, version: 0 });
export const useShell = () => useContext(ShellContext);
