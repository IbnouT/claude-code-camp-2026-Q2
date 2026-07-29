import { useEffect, useState } from "react";
import type { SourceState } from "./types";

const fallback: SourceState[] = [
  {
    id: "gateway",
    label: "Gateway journal",
    state: "unavailable",
    detail: "Capability status is loading",
  },
  {
    id: "agent",
    label: "Agent events",
    state: "disabled",
    detail: "Not configured",
  },
  {
    id: "benchmark",
    label: "Benchmark evidence",
    state: "disabled",
    detail: "Not configured",
  },
  {
    id: "knowledge",
    label: "Knowledge store",
    state: "disabled",
    detail: "Not configured",
  },
];

export function useCapabilities(): SourceState[] {
  const [sources, setSources] = useState<SourceState[]>(fallback);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/capabilities", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("capability discovery failed");
        }
        return response.json() as Promise<{ sources: SourceState[] }>;
      })
      .then((payload) => setSources(payload.sources))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setSources(fallback);
      });
    return () => controller.abort();
  }, []);

  return sources;
}
