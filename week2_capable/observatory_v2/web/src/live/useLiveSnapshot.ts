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

export function useLiveSnapshot(identity: LiveRouteIdentity | null): {
  snapshot: Snapshot | null;
  state: LiveSnapshotState;
} {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [state, setState] = useState<LiveSnapshotState>("loading");

  useEffect(() => {
    setSnapshot(null);
    setState("loading");
    if (identity === null) return;
    const controller = new AbortController();
    let timer = 0;
    const load = () => {
      fetch(`/api/sessions/${encodeURIComponent(identity.sessionId)}/snapshot`, {
        cache: "no-store",
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Snapshot unavailable (${response.status})`);
          }
          return response.json() as Promise<unknown>;
        })
        .then((value) => {
          setSnapshot(decodeSnapshot(value));
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
  }, [identity]);

  return { snapshot, state };
}
