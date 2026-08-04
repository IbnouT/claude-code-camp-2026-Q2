import { Link } from "@tanstack/react-router"
import { useEffect, useMemo, useState } from "react"

import { cn } from "@/lib/utils"

import { Constellation } from "./launcher-backdrop"
import {
  buildRoster,
  duration,
  endedSessions,
  observedNumber,
  stopAnnotation,
  when,
  type ResetMode,
  type RosterRow,
  type StartIntent,
} from "./launcher-model"
import type { PlayerOption, SessionCatalogItem } from "@/data/session-catalog"
import type { VitalsFields } from "@/data/session-vitals"

type LauncherStatus = "pending" | "error" | "ready"

type LauncherViewProps = {
  status: LauncherStatus
  players: readonly PlayerOption[]
  sessions: readonly SessionCatalogItem[]
  onStart: (intent: StartIntent) => void
  onRetry?: () => void
  starting?: boolean
  startError?: string
  errorDetail?: string
  selectedId?: string
  onSelectPlayer?: (playerId: string) => void
  vitals?: { playerId: string; fields: VitalsFields }
  initialLoadOpen?: boolean
}

const menuItemClassName =
  "relative rounded-launcher-card border border-line bg-surface/80 shadow-[0_1px_2px_rgb(15_30_45/0.05),0_10px_30px_rgb(15_30_45/0.07)] pt-[18px] pr-5 pb-[18px] pl-6 backdrop-blur-[4px] transition-[border-color,transform] duration-150 " +
  "before:absolute before:left-0 before:top-3.5 before:bottom-3.5 before:w-[3px] before:rounded-[3px] before:bg-line-strong " +
  "hover:translate-x-1 hover:border-accent hover:before:bg-accent"

/* The agent's real progress; null until the projection has materialized. */
function progressLabel(session: SessionCatalogItem): string | null {
  if (session.turn_count === null || session.iteration_count === null) {
    return null
  }
  return `Turn ${session.turn_count} · it ${session.iteration_count}`
}

/* 8px pulsing dot marking a live session. */
function LiveDot() {
  return (
    <i
      aria-hidden="true"
      className="inline-block size-2 animate-pulse-glow rounded-full bg-accent shadow-[0_0_10px_var(--accent)]"
    />
  )
}

/* Right-aligned recency block on a roster row. */
function Seen({ latest }: { latest: SessionCatalogItem }) {
  return (
    <span className="ml-auto text-right text-launcher-fine leading-[1.5] whitespace-nowrap text-content-quiet">
      {latest.live ? (
        <>
          LIVE now
          {progressLabel(latest) === null ? null : (
            <>
              <br />
              {progressLabel(latest)}
            </>
          )}
        </>
      ) : (
        <>
          last session
          <br />
          {when(latest.updated_at)}
        </>
      )}
    </span>
  )
}

/* Observed stat readout for the selected roster card. */
function VitalsBar({
  name,
  current,
  max,
  fillClassName,
}: {
  name: string
  current: number
  max: number
  fillClassName: string
}) {
  const width = `${Math.min(100, (current / max) * 100)}%`
  return (
    <div className="flex items-center gap-[9px] text-launcher-caption text-content-quiet">
      <span className="w-[34px]">{name}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-[5px] bg-surface-soft">
        <i
          className={cn("block h-full rounded-[5px]", fillClassName)}
          style={{ width }}
        />
      </span>
      <span className="w-[70px] text-right text-content-muted">
        {current} / {max}
      </span>
    </div>
  )
}

/* Compact readout for a non-active row whose stats are already loaded. */
function CompactStatus({ fields }: { fields: VitalsFields }) {
  const hp = observedNumber(fields, "hp", "hit", "hitpoints")
  const maxHp = observedNumber(fields, "max_hp", "max_hit", "maxhit")
  const level = observedNumber(fields, "level")
  return (
    <>
      {level !== null ? (
        <div className="mt-[3px] text-launcher-fine text-warning">
          Level {level}
        </div>
      ) : null}
      {hp !== null && maxHp !== null ? (
        <div className="mt-[5px] h-1 w-[120px] overflow-hidden rounded-[4px] bg-surface-soft">
          <i
            className="block h-full bg-[linear-gradient(90deg,#2e7d5b,var(--success))]"
            style={{ width: `${Math.min(100, (hp / maxHp) * 100)}%` }}
          />
        </div>
      ) : null}
    </>
  )
}

function StatusBars({ fields }: { fields: VitalsFields }) {
  const hp = observedNumber(fields, "hp", "hit", "hitpoints")
  const maxHp = observedNumber(fields, "max_hp", "max_hit", "maxhit")
  const mana = observedNumber(fields, "mana")
  const maxMana = observedNumber(fields, "max_mana", "maxmana")
  const level = observedNumber(fields, "level")
  const gold = observedNumber(fields, "gold")
  return (
    <>
      {level !== null ? (
        <div className="mt-[3px] text-launcher-fine text-warning">
          Level {level} adventurer
        </div>
      ) : null}
      <div className="mt-3 flex flex-col gap-[7px]">
        {hp !== null && maxHp !== null ? (
          <VitalsBar
            name="HP"
            current={hp}
            max={maxHp}
            fillClassName="bg-[linear-gradient(90deg,#2e7d5b,var(--success))]"
          />
        ) : null}
        {mana !== null && maxMana !== null ? (
          <VitalsBar
            name="Mana"
            current={mana}
            max={maxMana}
            fillClassName="bg-[linear-gradient(90deg,#2b5f8f,#7ec3f0)]"
          />
        ) : null}
      </div>
      {gold !== null ? (
        <div className="mt-2.5 text-launcher-detail text-warning">
          ◉ {gold.toLocaleString()} gold
        </div>
      ) : null}
      <div className="mt-[7px] text-launcher-fine text-content-quiet">
        stats as observed in the last session
      </div>
    </>
  )
}

function LauncherView({
  status,
  players,
  sessions,
  onStart,
  onRetry,
  starting = false,
  startError,
  errorDetail,
  selectedId: controlledSelectedId,
  onSelectPlayer,
  vitals,
  initialLoadOpen = false,
}: LauncherViewProps) {
  const roster = useMemo(
    () => buildRoster(players, sessions),
    [players, sessions]
  )
  const liveSessions = useMemo(
    () => sessions.filter((session) => session.live),
    [sessions]
  )
  const [internalSelectedId, setInternalSelectedId] = useState<
    string | undefined
  >(undefined)
  const selectedId = controlledSelectedId ?? internalSelectedId
  const selectPlayer = onSelectPlayer ?? setInternalSelectedId
  const [objective, setObjective] = useState("")
  const [temple, setTemple] = useState(false)
  const [baseline, setBaseline] = useState(false)
  const [startOpen, setStartOpen] = useState(true)
  const [loadOpen, setLoadOpen] = useState(initialLoadOpen)
  const [allPlayers, setAllPlayers] = useState(false)

  const selected: RosterRow | undefined =
    roster.find((row) => row.id === selectedId) ?? roster[0]

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setStartOpen(false)
        setLoadOpen(false)
      }
    }
    window.addEventListener("keydown", close)
    return () => {
      window.removeEventListener("keydown", close)
    }
  }, [])
  const selectedLive = selected?.latest?.live === true
  const reset: ResetMode = baseline ? "baseline" : temple ? "temple" : "none"
  const ended = useMemo(
    () => endedSessions(sessions, selected?.id, allPlayers),
    [sessions, selected?.id, allPlayers]
  )
  const selectedEndedCount = useMemo(
    () =>
      sessions.filter(
        (session) => !session.live && session.player_id === selected?.id
      ).length,
    [sessions, selected?.id]
  )
  const allEndedCount = useMemo(
    () => sessions.filter((session) => !session.live).length,
    [sessions]
  )

  return (
    <main className="relative min-h-screen overflow-hidden text-launcher-base leading-[normal] text-content-primary">
      <Constellation live={liveSessions.length > 0} />

      {starting ? (
        <output className="fixed inset-0 z-20 grid place-items-center bg-[rgb(7_11_16/72%)] backdrop-blur-[7px]">
          <div className="min-w-[min(360px,calc(100vw-40px))] rounded-launcher-card border border-accent/35 bg-surface/90 px-7 py-6 text-center shadow-[0_20px_70px_rgb(0_0_0/42%)]">
            <span
              aria-hidden="true"
              className="inline-block size-2.5 animate-[pulse-glow_1.1s_ease-in-out_infinite] rounded-full bg-accent shadow-[0_0_16px_var(--accent)]"
            />
            <p className="mt-3 mb-1 text-launcher-heading font-semibold text-content-primary">
              Starting {selected?.label ?? "the agent"}
            </p>
            <small className="text-launcher-detail text-content-muted">
              Connecting the agent and opening Live automatically…
            </small>
          </div>
        </output>
      ) : null}

      <div className="relative flex min-h-screen items-center justify-center gap-[54px] p-10 max-[850px]:flex-col max-[850px]:items-stretch">
        <section className="w-[360px] max-[850px]:mx-auto max-[850px]:w-[min(100%,440px)]">
          <header>
            <h1 className="text-launcher-title leading-[1.2] font-bold tracking-[0.04em]">
              Boukensha
              <br />
              <b className="font-semibold text-accent">Observatory</b>
            </h1>
            <p className="mt-2 text-launcher-note text-content-quiet">
              Watch an agent live inside the world of Arcane Loop.
            </p>
          </header>

          {status === "error" ? (
            <div className="mt-[22px] text-lifecycle-failed">
              {errorDetail ?? "Sessions unavailable"}{" "}
              {onRetry ? (
                <button
                  type="button"
                  onClick={onRetry}
                  className="ml-2 cursor-pointer rounded-launcher-retry border border-line bg-surface-raised px-2 py-0.5 text-content-primary"
                >
                  Retry
                </button>
              ) : null}
            </div>
          ) : null}

          {status === "pending" ? (
            <div
              aria-label="Loading adventurers"
              className="mt-[26px] h-[100px] w-full animate-pulse-glow rounded-launcher-row bg-[linear-gradient(90deg,var(--surface),var(--surface-raised),var(--surface))]"
            />
          ) : null}

          <div className="mt-[26px] flex flex-col gap-2.5">
            {roster.map((row) => {
              const active = row.id === selected?.id
              return (
                <button
                  key={row.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => selectPlayer(row.id)}
                  className={cn(
                    "block w-full cursor-pointer rounded-launcher-row border text-left",
                    active
                      ? "border-accent bg-[linear-gradient(180deg,var(--surface-raised),var(--surface))] px-4 py-3.5 shadow-[0_0_0_1px_var(--accent-soft)]"
                      : "border-line bg-surface px-3.5 py-[11px] hover:border-line-strong"
                  )}
                >
                  <span className="flex items-start gap-3">
                    <span
                      className={cn(
                        "grid flex-none place-items-center rounded-launcher-sigil bg-accent-soft text-accent",
                        active
                          ? "size-11 text-launcher-sigil-lg"
                          : "size-9 text-launcher-sigil"
                      )}
                    >
                      {row.latest?.live ? "⚔" : "◎"}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          "flex items-center gap-2 font-semibold",
                          active
                            ? "text-launcher-heading"
                            : "text-launcher-name"
                        )}
                      >
                        {row.label}
                        {row.latest?.live ? <LiveDot /> : null}
                      </span>
                      {!row.latest ? (
                        <span className="mt-1 block text-launcher-caption text-content-quiet">
                          no sessions yet
                        </span>
                      ) : null}
                      {active && vitals?.playerId === row.id ? (
                        <StatusBars fields={vitals.fields} />
                      ) : null}
                      {!active && vitals?.playerId === row.id ? (
                        <CompactStatus fields={vitals.fields} />
                      ) : null}
                    </span>
                    {row.latest ? <Seen latest={row.latest} /> : null}
                  </span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="flex w-[400px] flex-col gap-3 max-[850px]:mx-auto max-[850px]:w-[min(100%,440px)]">
          {liveSessions.map((session) => (
            <Link
              key={session.id}
              to="/live"
              search={{
                player: session.player_id,
                session: session.id,
                view: "overview",
              }}
              className={cn(
                menuItemClassName,
                "block border-accent/35 no-underline"
              )}
            >
              <h2 className="flex items-center gap-2.5 text-launcher-heading font-bold tracking-[0.05em] text-accent">
                <LiveDot /> WATCH LIVE{" "}
                <span className="ml-auto text-launcher-caption tracking-normal text-content-quiet">
                  {session.character}
                  {progressLabel(session) === null
                    ? ""
                    : ` · ${progressLabel(session)}`}
                </span>
              </h2>
              <p className="mt-launcher-text text-launcher-detail text-content-muted">
                {session.character} is exploring right now. Join the run in
                progress.
              </p>
            </Link>
          ))}

          <section
            className={cn(
              menuItemClassName,
              selectedLive ? "opacity-[0.66]" : ""
            )}
          >
            <button
              type="button"
              onClick={() => setStartOpen((open) => !open)}
              className="w-full cursor-pointer text-left"
            >
              <h2 className="flex items-center gap-2.5 text-launcher-heading font-bold tracking-[0.05em]">
                ⚔ START A NEW SESSION{" "}
                <span className="ml-auto rounded-launcher-control bg-accent-soft px-2.5 py-[3px] text-launcher-chip tracking-normal text-accent">
                  as {selected?.label ?? "player"}
                </span>
              </h2>
              <p className="mt-launcher-text text-launcher-detail text-content-muted">
                {selectedLive
                  ? `${selected?.label} is live. Watch or wait.`
                  : "Send the selected adventurer back into the world."}
              </p>
            </button>
            {startOpen ? (
              <form
                className="mt-3.5 flex flex-col gap-2.5"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (!selected || selectedLive || !selected.startAvailable)
                    return
                  onStart({
                    playerId: selected.id,
                    objective: objective.trim(),
                    reset,
                  })
                }}
              >
                <label
                  htmlFor="launcher-objective"
                  className="grid gap-1.5 text-launcher-caption tracking-[0.08em] text-content-muted uppercase"
                >
                  <span>
                    Opening instruction <em>optional</em>
                  </span>
                  <textarea
                    id="launcher-objective"
                    value={objective}
                    disabled={starting || selectedLive}
                    onChange={(event) => setObjective(event.target.value)}
                    maxLength={4000}
                    rows={3}
                    placeholder="Leave empty to start the agent idle"
                    className="w-full resize-y rounded-launcher-control border border-line bg-surface/70 px-2.5 py-[9px] text-launcher-detail leading-[1.45] tracking-normal text-content-primary normal-case outline-none placeholder:text-content-quiet focus:border-accent"
                  />
                </label>
                <div className="flex gap-[22px] text-launcher-note text-content-muted">
                  <label
                    className="flex cursor-pointer items-center gap-1.5"
                    title="Move the player to the Temple of Midgaard before the session starts. Stats and items are untouched."
                  >
                    <input
                      type="checkbox"
                      checked={temple}
                      disabled={starting || selectedLive}
                      onChange={(event) => {
                        setTemple(event.target.checked)
                        if (event.target.checked) setBaseline(false)
                      }}
                      className="mt-[3px] mr-[3px] mb-[3px] ml-[4px] accent-[var(--accent)]"
                    />
                    Reset to Temple
                  </label>
                  <label
                    className="flex cursor-pointer items-center gap-1.5"
                    title="Restore the player to the versioned baseline start. Inventory is untouched."
                  >
                    <input
                      type="checkbox"
                      checked={baseline}
                      disabled={starting || selectedLive}
                      onChange={(event) => {
                        setBaseline(event.target.checked)
                        if (event.target.checked) setTemple(false)
                      }}
                      className="mt-[3px] mr-[3px] mb-[3px] ml-[4px] accent-[var(--accent)]"
                    />
                    Reset to baseline
                  </label>
                </div>
                <p className="mt-launcher-text text-launcher-caption text-content-quiet">
                  Unchecked resumes the game normally.
                </p>
                <button
                  type="submit"
                  disabled={starting || !selected || selectedLive}
                  className="cursor-pointer self-end rounded-launcher-action border border-accent/30 bg-accent-soft px-4 py-2 text-launcher-note font-semibold text-accent disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {starting
                    ? "Starting…"
                    : `Start session as ${selected?.label ?? "player"} →`}
                </button>
                {startError ? (
                  <p
                    role="alert"
                    className="mt-launcher-text text-right text-launcher-detail text-warning"
                  >
                    {startError}
                  </p>
                ) : null}
              </form>
            ) : null}
          </section>

          <section className={menuItemClassName}>
            <button
              type="button"
              onClick={() => setLoadOpen((open) => !open)}
              className="w-full cursor-pointer text-left"
            >
              <h2 className="flex items-center gap-2.5 text-launcher-heading font-bold tracking-[0.05em]">
                ▤ LOAD A SESSION{" "}
                <span className="ml-auto text-launcher-caption tracking-normal text-content-quiet">
                  {selected?.label ?? "player"} · {selectedEndedCount} of{" "}
                  {allEndedCount}
                </span>
              </h2>
              <p className="mt-launcher-text text-launcher-detail text-content-muted">
                Replay any recorded run of the selected player, or all players.
              </p>
            </button>
            {loadOpen ? (
              <div className="mt-3 flex flex-col gap-[7px]">
                <label className="flex cursor-pointer items-center gap-1.5 text-launcher-caption text-content-muted">
                  <input
                    type="checkbox"
                    checked={allPlayers}
                    onChange={(event) => setAllPlayers(event.target.checked)}
                    className="mt-[3px] mr-[3px] mb-[3px] ml-[4px] accent-[var(--accent)]"
                  />{" "}
                  All players
                </label>
                {ended.length === 0 ? (
                  <p className="mt-launcher-text rounded-launcher-list border border-dashed border-line p-2 text-launcher-detail text-content-quiet">
                    No recorded sessions yet.
                  </p>
                ) : null}
                {ended.map((session) => (
                  <Link
                    key={session.id}
                    to="/sessions"
                    search={{
                      player: session.player_id,
                      session: session.id,
                      page: 1,
                      state: "all",
                    }}
                    className="flex justify-between rounded-launcher-list border border-line bg-surface-raised p-2 text-left text-launcher-fine text-content-muted no-underline transition-colors hover:border-accent"
                  >
                    <span>
                      {allPlayers ? `${session.character} · ` : ""}
                      {when(session.updated_at)}
                    </span>
                    <span>
                      {stopAnnotation(session)}
                      {session.event_count ?? 0} events · {duration(session)} ·
                      Load →
                    </span>
                  </Link>
                ))}
              </div>
            ) : null}
          </section>
        </section>
      </div>
    </main>
  )
}

export { LauncherView }
export type { LauncherStatus, LauncherViewProps }
