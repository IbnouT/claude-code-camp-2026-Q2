import {
  useEffect,
  useState,
} from "react";
import {
  decodeSnapshot,
  type Snapshot,
} from "../contracts";
import type { LiveRouteIdentity } from "../routes";

export type LiveSnapshotState = "loading" | "ready" | "reconnecting";

async function fetchSnapshot(
  url: string,
  signal: AbortSignal,
): Promise<Snapshot> {
  const response = await fetch(url, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(`Snapshot unavailable (${response.status})`);
  }
  return decodeSnapshot(await response.json() as unknown);
}

export function useLiveSnapshot(
  identity: LiveRouteIdentity | null,
  throughSequence: number | null = null,
): {
  latestSnapshot: Snapshot | null;
  snapshot: Snapshot | null;
  state: LiveSnapshotState;
} {
  const [latestSnapshot, setLatestSnapshot] = useState<Snapshot | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [state, setState] = useState<LiveSnapshotState>("loading");

  useEffect(() => {
    setLatestSnapshot(null);
    setSnapshot(null);
    setState("loading");
    if (identity === null) return;
    const controller = new AbortController();
    let timer = 0;
    const load = () => {
      const url = `/api/sessions/${encodeURIComponent(identity.sessionId)}/snapshot`;
      const request = throughSequence === null
        ? fetchSnapshot(url, controller.signal).then(
          (nextSnapshot) => [nextSnapshot, nextSnapshot] as const,
        )
        : Promise.all([
          fetchSnapshot(url, controller.signal),
          fetchSnapshot(`${url}?through=${throughSequence}`, controller.signal),
        ]);
      request
        .then(([nextLatestSnapshot, nextSnapshot]) => {
          setLatestSnapshot(nextLatestSnapshot);
          setSnapshot(nextSnapshot);
          setState("ready");
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") {
            return;
          }
          setState("reconnecting");
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            timer = window.setTimeout(load, 2_000);
          }
        });
    };
    load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [identity, throughSequence]);

  return { latestSnapshot, snapshot, state };
}
