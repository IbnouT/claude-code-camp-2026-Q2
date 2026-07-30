import { useEffect, useState } from "react";
import type { AtlasProjectionData } from "./worldContracts";

export function useAtlas(zone: number | null) {
  const [atlas, setAtlas] = useState<AtlasProjectionData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    const query = zone === null
      ? ""
      : `?level=zone&zone=${encodeURIComponent(zone)}`;
    void fetch(`/api/world/atlas${query}`, { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`World atlas returned ${response.status}`);
        }
        return await response.json() as AtlasProjectionData;
      })
      .then((payload) => {
        setAtlas(payload);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Atlas unavailable");
        }
      });
    return () => abort.abort();
  }, [zone]);

  return { atlas, error };
}
