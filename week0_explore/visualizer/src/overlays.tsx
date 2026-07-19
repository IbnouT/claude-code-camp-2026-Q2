// Activity-layer overlays: combat panel, terminal drawer, toasts, voice.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { StateC } from "./state";

export const ACTIVITY_META: Record<string, { icon: string; color: string }> = {
  fighting: { icon: "⚔", color: "var(--critical)" },
  resting: { icon: "💤", color: "var(--good)" },
  shopping: { icon: "🪙", color: "var(--gold)" },
  reading: { icon: "📖", color: "var(--accent)" },
  exploring: { icon: "🧭", color: "var(--aqua)" },
  thinking: { icon: "🤔", color: "var(--ink-2)" },
  dead: { icon: "☠", color: "var(--critical)" },
  busy: { icon: "⚙", color: "var(--ink-2)" },
  idle: { icon: "·", color: "var(--ink-3)" },
};

/* ---------- combat spotlight ---------- */

export function CombatPanel({ combat }: { combat: StateC["combat"] }) {
  const scroller = useRef<HTMLDivElement>(null);
  const [last, setLast] = useState<StateC["combat"]>(null);
  const [outcome, setOutcome] = useState<string | null>(null);

  useEffect(() => {
    if (combat) {
      setLast(combat);
      setOutcome(null);
    } else if (last) {
      // fight just ended — read the outcome off the final lines
      const text = last.lines.join(" ");
      setOutcome(
        /You are dead/i.test(text) ? "☠ defeated" :
        /is dead!/i.test(text) ? "🏆 victory" :
        /flee/i.test(text) ? "🏃 fled" : "ended",
      );
      const t = setTimeout(() => { setLast(null); setOutcome(null); }, 3500);
      return () => clearTimeout(t);
    }
  }, [combat]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [combat?.lines.length]);

  const show = combat ?? last;
  if (!show) return null;
  return (
    <motion.div
      initial={{ y: 60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="absolute bottom-4 right-4 z-20 w-96 overflow-hidden rounded-lg border border-[var(--critical)]/50 bg-[var(--surface)]/95 shadow-2xl backdrop-blur"
    >
      <div className="flex items-center justify-between border-b border-[var(--hairline)] px-3 py-1.5">
        <span className="text-[12px] font-semibold tracking-wider text-[var(--critical)]">
          ⚔ FIGHTING {show.foe.toUpperCase()}
        </span>
        {outcome && (
          <motion.span initial={{ scale: 1.5 }} animate={{ scale: 1 }}
            className="text-[12px] font-semibold text-[var(--warning)]">
            {outcome}
          </motion.span>
        )}
      </div>
      <div ref={scroller} className="max-h-40 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-[var(--ink-2)]">
        {show.lines.map((l, i) => (
          <div key={i} style={{ color: lineColor(l) }}>{l}</div>
        ))}
      </div>
    </motion.div>
  );
}

function lineColor(l: string): string {
  if (/is dead!|death cry/i.test(l)) return "var(--good)";
  if (/hits you|You are dead|pounds you|crushes you/i.test(l)) return "var(--critical)";
  if (/You (hit|slash|pierce|pound|crush|whack|smite)/i.test(l)) return "var(--accent)";
  return "var(--ink-2)";
}

/* ---------- terminal drawer ---------- */

export function TerminalDrawer({ feed }: { feed: string[] }) {
  const [open, setOpen] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [feed.length, open]);
  return (
    <div className="absolute bottom-0 left-1/2 z-10 w-[46rem] max-w-[70%] -translate-x-1/2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="mx-auto block rounded-t-md border border-b-0 border-[var(--hairline)] bg-[var(--surface)] px-4 py-1 text-[11px] tracking-wider text-[var(--ink-3)] hover:text-[var(--ink-2)]"
      >
        {open ? "▾ hide terminal" : "▴ live terminal"}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 176 }}
            exit={{ height: 0 }}
            className="overflow-hidden border-t border-[var(--hairline)] bg-[#111110]/95 backdrop-blur"
          >
            <div ref={scroller} className="h-44 overflow-y-auto px-4 py-2 font-mono text-[11px] leading-relaxed text-[#9ba187]">
              {feed.length ? feed.map((l, i) => <div key={i}>{l}</div>)
                : <div className="text-[var(--ink-3)]">no session output yet</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------- big-moment toasts ---------- */

// The event log is a rotating window (capped server-side), so "what's new"
// must be found by overlap: the new list starts with some suffix of the old.
export function freshEvents(prev: string[], now: string[]): string[] {
  for (let m = Math.min(prev.length, now.length); m >= 0; m--) {
    let match = true;
    for (let i = 0; i < m; i++) {
      if (prev[prev.length - m + i] !== now[i]) { match = false; break; }
    }
    if (match) return now.slice(m);
  }
  return now;
}

export function Toasts({ events, deaths, ready }:
  { events: string[]; deaths: number; ready: boolean }) {
  const [banner, setBanner] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const seen = useRef<{ events: string[]; deaths: number; primed: boolean }>(
    { events: [], deaths: 0, primed: false });

  useEffect(() => {
    if (!ready) return; // wait for the first real payload before priming
    const s = seen.current;
    if (!s.primed) { // don't replay history on first load
      s.events = events; s.deaths = deaths; s.primed = true;
      return;
    }
    const fresh = freshEvents(s.events, events);
    s.events = events;
    const lvl = fresh.find((e) => /LEVEL UP/i.test(e));
    if (lvl) {
      setBanner(`★ ${lvl} ★`);
      setTimeout(() => setBanner(null), 3000);
    }
    if (deaths > s.deaths) {
      setFlash(true);
      setTimeout(() => setFlash(false), 1300);
    }
    s.deaths = deaths;
  }, [events, deaths, ready]);

  return (
    <>
      <AnimatePresence>
        {banner && (
          <motion.div
            initial={{ y: -40, opacity: 0, scale: 0.9 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="absolute left-1/2 top-14 z-30 -translate-x-1/2 rounded-lg border border-[var(--warning)]/60 bg-[var(--surface)] px-6 py-2.5 text-lg font-semibold text-[var(--warning)] shadow-2xl"
          >
            {banner}
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {flash && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="pointer-events-none absolute inset-0 z-30"
            style={{ boxShadow: "inset 0 0 140px 40px rgba(208,59,59,0.55)" }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

/* ---------- voice narration (browser TTS, zero deps) ---------- */

export function useVoice(state: StateC, ready: boolean):
  { voiceOn: boolean; toggle: () => void } {
  const [voiceOn, setVoiceOn] = useState(false);
  const seen = useRef<{ thought: string; events: string[]; primed: boolean }>(
    { thought: "", events: [], primed: false });
  const spoken = useRef({ text: "", at: 0 });
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // pick the nicest available system voice; quality order matters: the
  // Enhanced/Premium variants and Google's network voices sound natural,
  // the compact defaults (plain "Samantha") are the robotic ones
  useEffect(() => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    const pick = () => {
      const vs = synth.getVoices();
      const prefs = ["Premium", "Enhanced", "Google US English",
        "Google UK English Female", "Ava", "Zoe", "Samantha", "Allison",
        "Serena", "Karen", "Daniel"];
      voiceRef.current =
        prefs.map((p) => vs.find((v) => v.name.includes(p) && v.lang.startsWith("en")))
          .find(Boolean) ??
        vs.find((v) => v.lang.startsWith("en")) ?? vs[0] ?? null;
      if (voiceRef.current)
        console.info("[voice] using:", voiceRef.current.name);
    };
    pick();
    synth.addEventListener?.("voiceschanged", pick);
    return () => synth.removeEventListener?.("voiceschanged", pick);
  }, []);

  // whenever voice is off, keep the synth hard-stopped (Chrome's queue can
  // otherwise keep draining long after a cancel)
  useEffect(() => {
    if (!voiceOn) {
      window.speechSynthesis?.cancel();
      audioRef.current?.pause();
    }
  }, [voiceOn]);

  useEffect(() => {
    if (!ready) return; // don't prime (or speak) against the empty initial state
    const s = seen.current;
    if (!s.primed) {
      s.thought = state.thought; s.events = state.events; s.primed = true;
      return;
    }
    if (!voiceOn || !("speechSynthesis" in window)) {
      s.thought = state.thought; s.events = state.events;
      return;
    }
    // never queue (always replace with the newest line), and never repeat
    // the same line within 30s — caption sources can alternate and re-trigger
    const say = (text: string, pitch = 1) => {
      const now = Date.now();
      if (text === spoken.current.text && now - spoken.current.at < 30000) return;
      spoken.current = { text, at: now };
      if (state.tts) {
        // server-side neural TTS; browser voice only if it fails
        audioRef.current?.pause();
        const a = new Audio(`./speak?text=${encodeURIComponent(text)}`);
        audioRef.current = a;
        a.play().catch(() => sayBrowser(text, pitch));
        return;
      }
      sayBrowser(text, pitch);
    };
    const sayBrowser = (text: string, pitch: number) => {
      const synth = window.speechSynthesis;
      if (!synth) return;
      synth.cancel();
      const u = new SpeechSynthesisUtterance(text);
      if (voiceRef.current) u.voice = voiceRef.current;
      u.rate = 1.0;
      u.pitch = pitch;
      synth.speak(u);
    };
    const fresh = freshEvents(s.events, state.events);
    const lvl = fresh.find((e) => /LEVEL UP/i.test(e));
    const died = fresh.find((e) => /DIED/i.test(e));
    if (died) say("We died.", 0.7);          // big moments outrank narration
    else if (lvl) say(lvl, 1.3);
    else if (state.thought && state.thought !== s.thought) say(state.thought);
    s.thought = state.thought;
    s.events = state.events;
  }, [state.thought, state.events, voiceOn, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    voiceOn,
    toggle: () => {
      window.speechSynthesis?.cancel();
      audioRef.current?.pause();
      setVoiceOn((v) => !v);
    },
  };
}
