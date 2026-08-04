import {
  ChevronDownIcon,
  CircleStopIcon,
  DoorOpenIcon,
  ExternalLinkIcon,
  MapIcon,
  RadioIcon,
  RefreshCwIcon,
} from "lucide-react"
import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"

import {
  orderedSessions,
  sessionLifecycle,
  shortSessionId,
  type Lifecycle,
} from "@/app/session-context-model"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import type {
  SessionCatalogItem,
  SessionCatalogResult,
} from "@/data/session-catalog"
import { when } from "@/features/launcher/launcher-model"
import { SessionStopDialog } from "@/app/session-stop-dialog"

type SessionSelectorProps = {
  catalogResult: SessionCatalogResult
  isLoadingAllSessions: boolean
  loadAllSessions: () => Promise<void>
  onRefresh: () => Promise<void>
  onSelect: (session: SessionCatalogItem) => void
  onSelectPlayer: (playerId: string) => void
  playerComplete: boolean
  selected: SessionCatalogItem | null
  onLeaveLive?: () => void
}

const headingClassName =
  "mb-2 text-[9.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase"
const actionClassName =
  "inline-flex items-center gap-[7px] rounded-[9px] border border-line bg-surface-raised px-2.5 py-2 text-[10.5px] text-content-muted outline-none hover:border-line-strong hover:text-content-primary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-[0.56]"

function stateColor(lifecycle: string): string {
  if (lifecycle === "running") return "text-success"
  if (["checking", "draining", "reconnecting"].includes(lifecycle)) {
    return "text-warning"
  }
  return "text-content-quiet"
}

function sessionGoal(session: SessionCatalogItem): string | null {
  const goal = session.objective?.trim() ?? ""
  return goal === "" ? null : goal
}

function SessionRow({
  session,
  onOpen,
}: {
  session: SessionCatalogItem
  onOpen: (session: SessionCatalogItem) => void
}) {
  const lifecycle = sessionLifecycle(session)
  const goal = sessionGoal(session)
  return (
    <button
      type="button"
      aria-label={[
        lifecycle,
        goal ?? shortSessionId(session.id),
        when(session.updated_at),
        `${(session.event_count ?? 0).toLocaleString()} events`,
      ].join(", ")}
      className="grid w-full min-w-0 grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-2.5 rounded-[9px] px-2.5 py-[9px] text-left text-content-muted outline-none hover:bg-surface-raised hover:text-content-primary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
      onClick={() => onOpen(session)}
    >
      <span
        className={cn(
          "inline-flex items-center gap-[5px] text-[9.5px] capitalize",
          stateColor(lifecycle)
        )}
      >
        {session.live ? (
          <RadioIcon aria-hidden="true" className="size-3" />
        ) : null}
        {lifecycle}
      </span>
      {goal === null ? (
        <span className="grid min-w-0 gap-0.5">
          <strong className="truncate font-mono text-[10.5px] font-bold">
            {shortSessionId(session.id)}
          </strong>
          <small className="text-[9px] text-content-quiet">
            {when(session.updated_at)}
          </small>
        </span>
      ) : (
        <span className="grid min-w-0 gap-0.5">
          <strong className="truncate text-[10.5px] font-bold">{goal}</strong>
          <small className="truncate text-[9px] text-content-quiet">
            <span className="font-mono">{shortSessionId(session.id)}</span>
            {" · "}
            {when(session.updated_at)}
          </small>
        </span>
      )}
      <span className="text-[9.5px] whitespace-nowrap text-content-quiet">
        {(session.event_count ?? 0).toLocaleString()} events
      </span>
    </button>
  )
}

function ResultNotice({
  result,
  onRefresh,
}: {
  result: SessionCatalogResult
  onRefresh: () => Promise<void>
}) {
  if (result.status === "error") {
    return (
      <div className="grid gap-3 p-4">
        <p className="text-sm text-danger">Session catalog unavailable.</p>
        <button
          type="button"
          className="inline-flex w-fit items-center gap-2 rounded-[9px] border border-line px-3 py-2 text-[11px] text-content-primary outline-none hover:bg-surface-raised focus-visible:[box-shadow:var(--focus-ring)]"
          onClick={() => void onRefresh()}
        >
          <RefreshCwIcon aria-hidden="true" className="size-3.5" />
          Try again
        </button>
      </div>
    )
  }
  return <p className="p-4 text-sm text-content-muted">Loading sessions…</p>
}

/**
 * The header context switcher: current selection with its actions, the
 * player's recent sessions, and the other players, in the reference format.
 */
function SessionSelector({
  catalogResult,
  onRefresh,
  selected,
  onLeaveLive,
}: SessionSelectorProps) {
  const [contextOpen, setContextOpen] = useState(false)
  const [stopOpen, setStopOpen] = useState(false)
  const navigate = useNavigate()
  const catalog =
    catalogResult.status === "loading" || catalogResult.status === "error"
      ? undefined
      : catalogResult.data
  const lifecycle: Lifecycle | "idle" =
    selected === null ? "idle" : sessionLifecycle(selected)

  const openSession = (session: SessionCatalogItem) => {
    setContextOpen(false)
    if (session.live) {
      void navigate({
        to: "/live",
        search: {
          player: session.player_id,
          session: session.id,
          view: "overview",
        },
      })
      return
    }
    void navigate({
      to: "/sessions/$sessionId",
      params: { sessionId: session.id },
      search: { player: session.player_id, session: session.id },
    })
  }

  const playerSessions =
    catalog === undefined || selected === null
      ? []
      : orderedSessions(
          catalog.sessions.filter(
            (session) => session.player_id === selected.player_id
          )
        )
  const recent = playerSessions
    .filter((session) => session.id !== selected?.id)
    .slice(0, 3)
  return (
    <Popover open={contextOpen} onOpenChange={setContextOpen}>
      <PopoverTrigger
        aria-label={
          selected === null
            ? "Select player and session"
            : [
                "View context",
                selected.character || selected.player_id,
                lifecycle,
                shortSessionId(selected.id),
              ].join(", ")
        }
        className="inline-flex h-[34px] min-w-[252px] items-center justify-start gap-[7px] rounded-[11px] border border-line bg-surface-raised px-[13px] py-2 text-content-muted outline-none hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent max-[700px]:min-w-0"
      >
        {selected === null ? (
          <span className="truncate">Select context</span>
        ) : (
          <>
            <strong className="max-w-[180px] truncate text-[13px] font-medium text-content-primary">
              {selected.character || selected.player_id}
            </strong>
            <span aria-hidden="true">·</span>
            {lifecycle === "running" ? (
              <span
                aria-hidden="true"
                data-context-dot
                className="size-2 flex-none rounded-[50%] bg-success shadow-[0_0_0_3px_rgb(139_223_169/14%)]"
              />
            ) : null}
            <span
              data-context-state
              className={cn(
                "text-[12px] whitespace-nowrap lowercase",
                lifecycle === "running"
                  ? "text-success"
                  : ["checking", "draining", "reconnecting"].includes(lifecycle)
                    ? "text-warning"
                    : "text-content-muted"
              )}
            >
              {lifecycle}
            </span>
            <span aria-hidden="true">·</span>
            <span
              data-context-id
              className="text-[12px] whitespace-nowrap text-content-muted"
            >
              {shortSessionId(selected.id)}
            </span>
          </>
        )}
        <ChevronDownIcon
          aria-hidden="true"
          className="ml-auto size-[13px] flex-none"
        />
      </PopoverTrigger>
      <PopoverContent
        aria-label="View context"
        align="end"
        sideOffset={7}
        className="block max-h-[min(680px,calc(100vh-82px))] w-[min(420px,calc(100vw-2rem))] flex-row gap-[normal] overflow-y-auto rounded-[14px] border border-line-strong bg-surface p-0 leading-[normal] shadow-popover [--tw-ring-shadow:0_0_#0000]"
      >
        {catalog === undefined ? (
          <ResultNotice result={catalogResult} onRefresh={onRefresh} />
        ) : selected === null ? (
          <p className="p-4 text-sm text-content-muted">
            No session is available.
          </p>
        ) : (
          <>
            <section className="min-w-0 p-3">
              <p className={headingClassName}>Current</p>
              <div className="flex min-w-0 items-center justify-between gap-3 pt-[3px] pr-1 pb-2.5 pl-1">
                <span className="grid min-w-0 gap-[3px]">
                  <strong className="truncate text-[13px] font-bold text-content-primary">
                    {selected.character || selected.player_id}
                  </strong>
                  <small className="truncate font-mono text-[9px] text-content-quiet">
                    {selected.id}
                  </small>
                  {sessionGoal(selected) === null ? null : (
                    <small className="truncate text-[10px] text-content-muted">
                      {sessionGoal(selected)}
                    </small>
                  )}
                </span>
                <span
                  className={cn(
                    "text-[12px] whitespace-nowrap lowercase",
                    stateColor(lifecycle)
                  )}
                >
                  {lifecycle}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {onLeaveLive === undefined ? null : (
                  <button
                    type="button"
                    className={actionClassName}
                    onClick={() => {
                      setContextOpen(false)
                      onLeaveLive()
                    }}
                  >
                    <DoorOpenIcon aria-hidden="true" className="size-3.5" />
                    Leave Live view
                  </button>
                )}
                {lifecycle === "running" ? (
                  <button
                    type="button"
                    className={cn(actionClassName, "text-danger")}
                    onClick={() => {
                      setContextOpen(false)
                      setStopOpen(true)
                    }}
                  >
                    <CircleStopIcon aria-hidden="true" className="size-3.5" />
                    Stop session…
                  </button>
                ) : null}
                {!selected.live ? (
                  <button
                    type="button"
                    className={actionClassName}
                    onClick={() => {
                      setContextOpen(false)
                      void navigate({
                        to: "/sessions/$sessionId",
                        params: { sessionId: selected.id },
                        search: {
                          player: selected.player_id,
                          session: selected.id,
                          view: "map",
                        },
                      })
                    }}
                  >
                    <MapIcon aria-hidden="true" className="size-3.5" />
                    View map recording
                  </button>
                ) : null}
              </div>
            </section>

            {playerSessions.length > 0 ? (
              <section className="min-w-0 border-t border-line p-3">
                <p className={headingClassName}>
                  Recent {selected.character || selected.player_id} sessions
                </p>
                {recent.map((session) => (
                  <SessionRow
                    key={session.id}
                    session={session}
                    onOpen={openSession}
                  />
                ))}
              </section>
            ) : null}

            {playerSessions.length > 0 ? (
              <button
                type="button"
                className="flex w-full min-w-0 items-center justify-between gap-2.5 border-t border-line px-4 py-[11px] text-left text-[10.5px] text-content-muted outline-none hover:bg-surface-raised hover:text-content-primary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
                onClick={() => {
                  setContextOpen(false)
                  void navigate({
                    to: "/sessions",
                    search: {
                      player: selected.player_id,
                      session: selected.id,
                      page: 1,
                      state: "all",
                    },
                  })
                }}
              >
                View all {selected.character || selected.player_id} sessions (
                {playerSessions.length})
                <ExternalLinkIcon aria-hidden="true" className="size-[13px]" />
              </button>
            ) : null}
          </>
        )}
      </PopoverContent>
      {selected === null ? null : (
        <SessionStopDialog
          session={selected}
          open={stopOpen}
          onOpenChange={setStopOpen}
        />
      )}
    </Popover>
  )
}

export { SessionSelector, type SessionSelectorProps }
