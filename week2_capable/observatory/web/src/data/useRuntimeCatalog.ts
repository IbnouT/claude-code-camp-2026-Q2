import { useEffect, useState } from "react";
import {
  decodeCatalog,
  type RuntimeCatalog,
} from "./liveContracts";

const EMPTY: RuntimeCatalog = {
  version: 1,
  players: [],
  sessions: [],
};

export type RuntimeCatalogState = {
  catalog: RuntimeCatalog;
  loading: boolean;
  error: string | null;
};

export function useRuntimeCatalog(enabled = true): RuntimeCatalogState {
  const [state, setState] = useState<RuntimeCatalogState>({
    catalog: EMPTY,
    loading: true,
    error: null,
  });

  useEffect(() => {
    if (!enabled) {
      setState((current) => ({ ...current, loading: false }));
      return;
    }
    const abort = new AbortController();
    let timer = 0;

    const load = async () => {
      try {
        const response = await fetch("/api/sessions", {
          signal: abort.signal,
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`session discovery returned ${response.status}`);
        }
        const catalog = decodeCatalog(await response.json() as unknown);
        setState({ catalog, loading: false, error: null });
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState((current) => ({
            ...current,
            loading: false,
            error: error instanceof Error ? error.message : "session discovery failed",
          }));
        }
      } finally {
        if (!abort.signal.aborted) {
          timer = window.setTimeout(load, 2_000);
        }
      }
    };

    void load();
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, [enabled]);

  return state;
}
