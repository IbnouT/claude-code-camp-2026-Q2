import { useEffect, useMemo, useState } from "react";
import type {
  RecordedSessionCatalogItem,
  RecordedSessionInvestigation,
} from "./recordedSession";

type CatalogResponse = {
  sessions: RecordedSessionCatalogItem[];
};

export type RecordedSessionsState = {
  catalog: RecordedSessionCatalogItem[];
  investigation: RecordedSessionInvestigation | null;
  loadingCatalog: boolean;
  loadingInvestigation: boolean;
  error: string | null;
};

export function useRecordedSessions(
  selectedRun: string,
): RecordedSessionsState {
  const [catalog, setCatalog] = useState<RecordedSessionCatalogItem[]>([]);
  const [investigation, setInvestigation] =
    useState<RecordedSessionInvestigation | null>(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingInvestigation, setLoadingInvestigation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    let timer = 0;
    setLoadingCatalog(true);
    const load = async () => {
      try {
        const response = await fetch("/api/recorded-sessions", {
          signal: abort.signal,
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`recorded sessions returned ${response.status}`);
        }
        const payload = await response.json() as CatalogResponse;
        setCatalog(payload.sessions);
        setError(null);
      } catch (reason) {
        if (!abort.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Catalog unavailable");
        }
      } finally {
        if (!abort.signal.aborted) {
          setLoadingCatalog(false);
          timer = window.setTimeout(load, 2_000);
        }
      }
    };
    void load();
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!selectedRun) {
      setInvestigation(null);
      return;
    }
    const abort = new AbortController();
    setLoadingInvestigation(true);
    void fetch(
      `/api/recorded-sessions/${encodeURIComponent(selectedRun)}`,
      { signal: abort.signal },
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`recorded session returned ${response.status}`);
        }
        return await response.json() as RecordedSessionInvestigation;
      })
      .then((payload) => {
        setInvestigation(payload);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setInvestigation(null);
          setError(reason instanceof Error ? reason.message : "Session unavailable");
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoadingInvestigation(false);
      });
    return () => abort.abort();
  }, [selectedRun]);

  return useMemo(() => ({
    catalog,
    investigation,
    loadingCatalog,
    loadingInvestigation,
    error,
  }), [
    catalog,
    error,
    investigation,
    loadingCatalog,
    loadingInvestigation,
  ]);
}
