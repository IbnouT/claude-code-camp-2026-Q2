import { motion } from "framer-motion";
import type { Mode, StateC } from "../state";

export default function Cockpit({
  state,
  mode,
  lastChange,
  voiceOn,
  onToggleVoice,
}: {
  state: StateC;
  mode: Mode;
  lastChange: number;
  voiceOn: boolean;
  onToggleVoice: () => void;
}) {
  const v = state.vitals;
  const stale = Date.now() - lastChange > 5000;
  return (
    <aside className="flex h-full w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-[var(--hairline)] bg-[var(--surface)]/85 p-4 backdrop-blur">
      {/* header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold tracking-[0.2em] text-[var(--ink-3)]">
            MUD OBSERVATORY
          </div>
          <div className="text-sm text-[var(--ink-2)]">
            {state.position
              ? (state.rooms[state.position]?.title ?? state.position)
              : "position unknown"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onToggleVoice}
            title={voiceOn ? "voice narration on" : "voice narration off"}
            className={`rounded border px-1.5 py-0.5 text-[11px] ${
              voiceOn
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-[var(--hairline)] text-[var(--ink-3)] hover:text-[var(--ink-2)]"
            }`}
          >
            {voiceOn ? "🔊" : "🔇"}
          </button>
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              stale ? "bg-[var(--ink-3)]" : "bg-[var(--accent)] heartbeat-live"
            }`}
            title={stale ? "no state changes recently" : "receiving updates"}
          />
          <span className="rounded border border-[var(--hairline)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--ink-3)]">
            {mode}
          </span>
        </div>
      </div>

      {/* current activity strip */}
      {state.activity && state.activity.kind !== "idle" && (
        <div className="flex items-center gap-2 text-[12px] text-[var(--ink-2)]">
          <span className="rounded bg-[var(--surface-2)] px-2 py-0.5">
            {state.activity.detail}
          </span>
          {state.quiet_seconds != null && state.quiet_seconds >= 10 && (
            <span className="text-[var(--ink-3)]">quiet {state.quiet_seconds}s</span>
          )}
        </div>
      )}

      {/* thought line — caret only while fresh; older thoughts show their age */}
      {state.thought && (
        <div
          className="rounded-md border border-[var(--hairline)] bg-[var(--surface-2)] px-3 py-2 text-[13px] italic text-[var(--ink-2)]"
          style={{ opacity: (state.thought_age_s ?? 0) > 120 ? 0.55 : 1 }}
        >
          <span className="mr-1 text-[var(--accent)]">»</span>
          {state.thought}
          {(state.thought_age_s ?? 0) <= 45 ? (
            <span className="thought-caret text-[var(--accent)]">▌</span>
          ) : (
            <span className="ml-1.5 not-italic text-[11px] text-[var(--ink-3)]">
              ({fmtAge(state.thought_age_s!)} ago)
            </span>
          )}
        </div>
      )}

      {/* vitals */}
      <section className="flex flex-col gap-2.5">
        <Bar label="♥ HP" val={v.hp} max={v.max_hp} color={hpColor(v.hp, v.max_hp)} />
        <Bar label="✦ Mana" val={v.mana} max={v.max_mana} color="var(--accent)" />
        <Bar label="➤ Moves" val={v.moves} max={v.max_moves} color="var(--aqua)" />
      </section>

      {/* stat tiles */}
      <section className="grid grid-cols-3 gap-2">
        <Tile label="Level" value={v.level} />
        <Tile label="Gold" value={v.gold} accent="var(--gold)" />
        <Tile label="Deaths" value={state.deaths} accent={state.deaths ? "var(--critical)" : undefined} />
      </section>

      {/* xp progress */}
      {v.xp != null && v.xp_to_next != null && (
        <section>
          <div className="mb-1 flex justify-between text-[11px] text-[var(--ink-3)]">
            <span>XP → level {(v.level ?? 0) + 1}</span>
            <span>
              {v.xp} / {v.xp + v.xp_to_next}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-2)]">
            <div
              className="bar-fill h-full rounded-full"
              style={{
                width: `${Math.min(100, (100 * v.xp) / (v.xp + v.xp_to_next))}%`,
                backgroundColor: "var(--accent)",
              }}
            />
          </div>
        </section>
      )}

      {/* plan */}
      {state.plan && (state.plan.goal || state.plan.steps.length > 0) && (
        <section>
          <SectionTitle>PLAN</SectionTitle>
          <div className="mb-1.5 text-[13px] text-[var(--ink)]">{state.plan.goal}</div>
          <ol className="flex flex-col gap-1">
            {state.plan.steps.map((s, i) => {
              const isCurrent = !s.done && state.plan!.steps.findIndex((x) => !x.done) === i;
              return (
                <li
                  key={i}
                  className={`rounded-md px-2 py-1 text-[12.5px] ${
                    isCurrent
                      ? "border-l-2 border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--ink)]"
                      : s.done
                        ? "text-[var(--ink-3)] line-through decoration-[var(--ink-3)]/60"
                        : "text-[var(--ink-2)]"
                  }`}
                >
                  <motion.span
                    key={s.done ? "d" : "p"}
                    initial={s.done ? { scale: 1.6 } : false}
                    animate={{ scale: 1 }}
                    className={`mr-1.5 inline-block ${s.done ? "text-[var(--good)]" : "text-[var(--ink-3)]"}`}
                  >
                    {s.done ? "✓" : "○"}
                  </motion.span>
                  {s.text}
                  {s.check && !s.done && (
                    <span className="ml-1.5 rounded bg-[var(--surface-2)] px-1 py-px font-mono text-[10px] text-[var(--ink-3)]">
                      {s.check}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {/* event feed */}
      <section>
        <SectionTitle>EVENTS</SectionTitle>
        <ul className="flex flex-col gap-1">
          {state.events
            .slice(-8)
            .reverse()
            .map((e, i, arr) => (
              <motion.li
                key={`${state.events.length - i}-${e}`}
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
                className="flex items-start gap-1.5 text-[12.5px]"
                style={{ opacity: 1 - (i / Math.max(arr.length, 1)) * 0.55 }}
              >
                <span className="mt-px">{eventIcon(e)}</span>
                <span style={{ color: eventColor(e) }}>{e}</span>
              </motion.li>
            ))}
          {state.events.length === 0 && (
            <li className="text-[12px] text-[var(--ink-3)]">no events yet</li>
          )}
        </ul>
      </section>

      <div className="mt-auto pt-2 text-[10px] text-[var(--ink-3)]">
        {Object.keys(state.rooms).length} rooms mapped · polling 1s
      </div>
    </aside>
  );
}

function fmtAge(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 text-[10px] font-semibold tracking-[0.18em] text-[var(--ink-3)]">
      {children}
    </div>
  );
}

function Bar({
  label,
  val,
  max,
  color,
}: {
  label: string;
  val?: number | null;
  max?: number | null;
  color: string;
}) {
  const pct = val != null && max ? Math.max(0, Math.min(100, (100 * val) / max)) : null;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px]">
        <span className="text-[var(--ink-2)]">{label}</span>
        <span className="font-mono text-[var(--ink-3)]">
          {val ?? "—"}
          {max ? ` / ${max}` : ""}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-2)]">
        {pct !== null && (
          <div
            className="bar-fill h-full rounded-full"
            style={{ width: `${pct}%`, backgroundColor: color }}
          />
        )}
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value?: number | null;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] px-2 py-1.5 text-center">
      <div className="text-lg font-semibold" style={{ color: accent ?? "var(--ink)" }}>
        {value ?? "—"}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">{label}</div>
    </div>
  );
}

function hpColor(hp?: number | null, max?: number | null): string {
  if (hp == null || !max) return "var(--good)";
  const r = hp / max;
  if (r > 0.5) return "var(--good)";
  if (r > 0.25) return "var(--warning)";
  return "var(--critical)";
}

function eventIcon(e: string): string {
  if (/DIED|dead/i.test(e) && /you|DIED/i.test(e)) return "☠";
  if (/^Killed/i.test(e)) return "⚔";
  if (/LEVEL UP/i.test(e)) return "★";
  if (/gold|Bought|coins/i.test(e)) return "◆";
  return "·";
}

function eventColor(e: string): string {
  if (/DIED/i.test(e)) return "var(--critical)";
  if (/^Killed/i.test(e)) return "var(--good)";
  if (/LEVEL UP/i.test(e)) return "var(--warning)";
  if (/gold|Bought/i.test(e)) return "var(--gold)";
  return "var(--ink-2)";
}
