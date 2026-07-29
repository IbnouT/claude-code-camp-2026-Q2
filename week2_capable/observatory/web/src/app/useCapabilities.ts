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

export type CapabilityState = {
  sources: SourceState[];
  features: string[];
};

export function useCapabilities(): CapabilityState {
  const [sources, setSources] = useState<SourceState[]>(fallback);
  const [features, setFeatures] = useState<string[]>([
    "live",
    "diagnostics",
    "compare",
  ]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/capabilities", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("capability discovery failed");
        }
        return response.json() as Promise<CapabilityState>;
      })
      .then((payload) => {
        setSources(payload.sources);
        setFeatures(payload.features);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setSources(fallback);
      });
    return () => controller.abort();
  }, []);

  return { sources, features };
}
