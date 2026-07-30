import { useEffect, useState } from "react";
import type { DiagnosticHistory } from "./incidents";

const emptyHistory: DiagnosticHistory = {
  player_id: null,
  total_runs: 0,
  successful_runs: 0,
  failed_runs: 0,
  items: [],
};

export function useDiagnosticHistory(playerId: string, enabled: boolean) {
  const [history, setHistory] = useState<DiagnosticHistory>(emptyHistory);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !playerId) {
      setHistory(emptyHistory);
      setError(null);
      return;
    }
    const abort = new AbortController();
    void fetch(
      `/api/diagnostic-history?player=${encodeURIComponent(playerId)}`,
      { cache: "no-store", signal: abort.signal },
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`diagnostic history returned ${response.status}`);
        }
        return await response.json() as DiagnosticHistory;
      })
      .then((payload) => {
        if (!abort.signal.aborted) setHistory(payload);
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Diagnostic history is unavailable",
          );
        }
      });
    return () => abort.abort();
  }, [enabled, playerId]);

  return { history, error };
}
