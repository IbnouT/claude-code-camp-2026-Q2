// The contract — the ONLY shape the UI knows. serve.py adapts the play-mud
// store into this; a future week-1/2 loop can write it directly.

export interface RoomC {
  title: string;
  exits: string[]; // full direction names, may include "up"/"down"
  flags: string[]; // "hazard" | "death" | "dark"
  hazards: string[]; // raw hazard notes, for hover detail
}

export interface LinkC {
  from: string;
  dir: string;
  to: string;
  ghost?: boolean; // known from `exits` output, never walked
}

export interface PlanStep {
  text: string;
  check?: string | null;
  done: boolean;
}

export interface Vitals {
  hp?: number | null;
  max_hp?: number | null;
  mana?: number | null;
  max_mana?: number | null;
  moves?: number | null;
  max_moves?: number | null;
  gold?: number | null;
  xp?: number | null;
  xp_to_next?: number | null;
  level?: number | null;
}

export type ActivityKind =
  | "fighting" | "resting" | "shopping" | "reading" | "exploring"
  | "thinking" | "dead" | "busy" | "idle";

export interface Activity {
  kind: ActivityKind;
  detail: string;
}

export interface StateC {
  rooms: Record<string, RoomC>;
  links: LinkC[];
  trail: LinkC[]; // oldest first
  position: string | null;
  vitals: Vitals;
  deaths: number;
  events: string[];
  plan: { goal: string; steps: PlanStep[] } | null;
  thought: string;
  thought_age_s?: number | null;
  activity: Activity | null;
  combat: { foe: string; lines: string[] } | null;
  feed: string[]; // last raw game lines
  quiet_seconds: number | null;
  tts?: boolean; // server-side OpenAI TTS available
  hash?: string;
}

export const EMPTY_STATE: StateC = {
  rooms: {},
  links: [],
  trail: [],
  position: null,
  vitals: {},
  deaths: 0,
  events: [],
  plan: null,
  thought: "",
  activity: null,
  combat: null,
  feed: [],
  quiet_seconds: null,
};

export type Mode = "live" | "demo" | "waiting";

import { useEffect, useRef, useState } from "react";
import { demoFrame, DEMO_TICKS } from "./demo";

export function useGameState(): {
  state: StateC;
  mode: Mode;
  lastChange: number;
  ready: boolean; // first real payload received — before this, don't react
} {
  const demo = new URLSearchParams(window.location.search).has("demo");
  const [state, setState] = useState<StateC>(EMPTY_STATE);
  const [mode, setMode] = useState<Mode>(demo ? "demo" : "waiting");
  const [lastChange, setLastChange] = useState<number>(Date.now());
  const [ready, setReady] = useState(false);
  const hashRef = useRef<string>("");

  useEffect(() => {
    if (demo) {
      let tick = 0;
      const id = setInterval(() => {
        setState(demoFrame(tick));
        setLastChange(Date.now());
        setReady(true);
        tick = (tick + 1) % DEMO_TICKS;
      }, 1100);
      return () => clearInterval(id);
    }
    let stop = false;
    const poll = async () => {
      try {
        const r = await fetch(`./state?hash=${hashRef.current}`);
        const j = await r.json();
        if (stop) return;
        if (!j.unchanged) {
          hashRef.current = j.hash ?? "";
          setState({ ...EMPTY_STATE, ...j });
          setMode(Object.keys(j.rooms ?? {}).length ? "live" : "waiting");
          setLastChange(Date.now());
        }
        setReady(true);
      } catch {
        if (!stop) setMode("waiting");
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [demo]);

  return { state, mode, lastChange, ready };
}
