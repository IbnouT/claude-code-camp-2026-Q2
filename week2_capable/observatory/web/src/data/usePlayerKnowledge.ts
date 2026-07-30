import { useEffect, useState } from "react";
import { emptyKnowledge, type PlayerKnowledge } from "./knowledge";

type Result = {
  knowledge: PlayerKnowledge;
  loading: boolean;
  error: string | null;
};

export function usePlayerKnowledge(playerId: string, revision = 0): Result {
  const [knowledge, setKnowledge] = useState<PlayerKnowledge>(emptyKnowledge);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!playerId) {
      setKnowledge(emptyKnowledge);
      setLoading(false);
      setError(null);
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    setError(null);
    fetch(`/api/players/${encodeURIComponent(playerId)}/knowledge`, {
      cache: "no-store",
      signal: abort.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json() as { detail?: string };
          throw new Error(
            payload.detail ?? `Knowledge returned ${response.status}`,
          );
        }
        return response.json() as Promise<PlayerKnowledge>;
      })
      .then((payload) => {
        if (!abort.signal.aborted) setKnowledge(payload);
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setError(
            reason instanceof Error ? reason.message : "Knowledge failed",
          );
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [playerId, revision]);

  return { knowledge, loading, error };
}
