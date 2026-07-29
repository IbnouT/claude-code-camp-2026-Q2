import { useEffect, useState } from "react";
import type { RunComparison } from "./comparison";

export function useComparison(): {
  comparison: RunComparison | null;
  loading: boolean;
} {
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    void fetch("/api/comparisons/j1-rendering-n10", {
      signal: abort.signal,
    })
      .then((response) => response.ok ? response.json() : null)
      .then((payload: RunComparison | null) => setComparison(payload))
      .catch(() => undefined)
      .finally(() => setLoading(false));
    return () => abort.abort();
  }, []);

  return { comparison, loading };
}
