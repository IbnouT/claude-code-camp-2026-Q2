import { useEffect, useMemo, useState } from "react";
import type { Investigation, RunSummary } from "./investigation";

type RunsResponse = {
  runs: RunSummary[];
};

export type InvestigationState = {
  runs: RunSummary[];
  selectedRun: string | null;
  investigation: Investigation | null;
  loading: boolean;
  selectRun: (runId: string) => void;
};

export function useInvestigation(): InvestigationState {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const abort = new AbortController();
    void fetch("/api/runs", { signal: abort.signal })
      .then((response) => response.ok ? response.json() : { runs: [] })
      .then((payload: RunsResponse) => {
        const ordered = [...payload.runs].sort((left, right) => {
          if (left.journey === "J2" && right.journey !== "J2") return -1;
          if (right.journey === "J2" && left.journey !== "J2") return 1;
          return right.attempt.localeCompare(left.attempt);
        });
        setRuns(ordered);
        const requested = new URL(window.location.href).searchParams.get("run");
        setSelectedRun(
          requested && ordered.some((run) => run.id === requested)
            ? requested
            : ordered[0]?.id ?? null,
        );
      })
      .catch(() => undefined);
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (selectedRun === null) {
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    void fetch(`/api/runs/${encodeURIComponent(selectedRun)}/investigation`, {
      signal: abort.signal,
    })
      .then((response) => response.ok ? response.json() : null)
      .then((payload: Investigation | null) => setInvestigation(payload))
      .catch(() => undefined)
      .finally(() => setLoading(false));
    return () => abort.abort();
  }, [selectedRun]);

  useEffect(() => {
    if (selectedRun === null) {
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("run", selectedRun);
    window.history.replaceState(null, "", url);
  }, [selectedRun]);

  return useMemo(() => ({
    runs,
    selectedRun,
    investigation,
    loading,
    selectRun: setSelectedRun,
  }), [investigation, loading, runs, selectedRun]);
}
