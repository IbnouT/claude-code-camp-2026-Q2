import {
  ChevronDownIcon,
  RefreshCwIcon,
  SearchIcon,
  TelescopeIcon,
  XIcon,
} from "lucide-react"
import { useMemo, useRef, useState } from "react"

import {
  formatSessionDate,
  latestSessions,
  orderedSessions,
  sessionLifecycle,
  sessionMatches,
  shortSessionId,
  type Lifecycle,
} from "@/app/session-context-model"
import {
  Modal,
  ModalBackdrop,
  ModalClose,
  ModalDescription,
  ModalPopup,
  ModalPortal,
  ModalTitle,
  ModalTrigger,
} from "@/components/ui/modal"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  SessionCatalog,
  SessionCatalogItem,
  SessionCatalogResult,
} from "@/data/session-catalog"

type SessionSelectorProps = {
  catalogResult: SessionCatalogResult
  isLoadingAllSessions: boolean
  loadAllSessions: () => Promise<void>
  onRefresh: () => Promise<void>
  onSelect: (session: SessionCatalogItem) => void
  onSelectPlayer: (playerId: string) => void
  playerComplete: boolean
  selected: SessionCatalogItem | null
}

function ContextStatus({
  lifecycle,
  label,
}: {
  lifecycle: Lifecycle
  label?: string
}) {
  return (
    <StatusBadge status={lifecycle} className="h-auto px-2 py-0.5 text-[10px]">
      {label ?? lifecycle}
    </StatusBadge>
  )
}

function SessionSummary({ session }: { session: SessionCatalogItem }) {
  const lifecycle = sessionLifecycle(session)

  return (
    <>
      <span className="min-w-0">
        <span className="flex items-center gap-2">
          <strong className="truncate text-[12px] font-semibold text-content-primary">
            {session.character || session.player_id}
          </strong>
          <ContextStatus lifecycle={lifecycle} />
        </span>
        <span className="mt-1 block truncate text-[10px] text-content-quiet">
          {session.objective || "No objective recorded"}
        </span>
      </span>
      <span className="text-right font-mono text-[9px] text-content-quiet">
        <span className="block">{shortSessionId(session.id)}</span>
        <span className="mt-1 block">
          {formatSessionDate(session.updated_at)}
        </span>
      </span>
    </>
  )
}

function SessionRow({
  session,
  onSelect,
}: {
  session: SessionCatalogItem
  onSelect: (session: SessionCatalogItem) => void
}) {
  return (
    <button
      type="button"
      aria-label={[
        session.character || session.player_id,
        sessionLifecycle(session),
        session.objective || "No objective recorded",
        session.id,
      ].join(", ")}
      className="grid w-full min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[9px] px-2.5 py-2 text-left outline-none hover:bg-surface-raised focus-visible:bg-surface-raised focus-visible:[box-shadow:inset_0_0_0_2px_var(--accent)]"
      onClick={() => onSelect(session)}
    >
      <SessionSummary session={session} />
    </button>
  )
}

function AllSessionsDialog({
  catalog,
  isLoadingAllSessions,
  loadAllSessions,
  onSelect,
  playerComplete,
}: {
  catalog: SessionCatalog
  isLoadingAllSessions: boolean
  loadAllSessions: () => Promise<void>
  onSelect: (session: SessionCatalogItem) => void
  playerComplete: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const searchRef = useRef<HTMLInputElement>(null)
  const matches = useMemo(
    () =>
      orderedSessions(catalog.sessions).filter((session) =>
        sessionMatches(session, query)
      ),
    [catalog.sessions, query]
  )

  return (
    <Modal
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen)
        if (nextOpen) {
          void loadAllSessions()
          window.setTimeout(() => searchRef.current?.focus(), 0)
        }
      }}
    >
      <ModalTrigger className="flex w-full items-center justify-between border-t border-line px-4 py-3 text-left text-[11px] font-semibold text-accent outline-none hover:bg-surface-raised focus-visible:[box-shadow:inset_0_0_0_2px_var(--accent)]">
        Show all sessions
        <span aria-hidden="true">
          {catalog.sessions.length}
          {playerComplete ? "" : "+"}
        </span>
      </ModalTrigger>
      <ModalPortal>
        <ModalBackdrop className="fixed inset-0 z-[100] bg-overlay backdrop-blur-xs" />
        <ModalPopup className="fixed top-1/2 left-1/2 z-[101] grid max-h-[min(720px,calc(100svh-2rem))] w-[min(680px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 grid-rows-[auto_auto_minmax(0,1fr)] overflow-hidden rounded-2xl border border-line-strong bg-surface shadow-popover outline-none">
          <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <span>
              <ModalTitle className="text-[17px] font-semibold">
                Sessions and players
              </ModalTitle>
              <ModalDescription className="mt-1 text-[11px] text-content-muted">
                Search by player, objective, lifecycle, or stable session
                identity.
              </ModalDescription>
            </span>
            <ModalClose
              aria-label="Close sessions dialog"
              className="grid size-8 place-items-center rounded-[9px] text-content-muted outline-none hover:bg-surface-raised hover:text-content-primary focus-visible:[box-shadow:var(--focus-ring)]"
            >
              <XIcon aria-hidden="true" className="size-4" />
            </ModalClose>
          </header>
          <label className="relative m-4 flex items-center">
            <span className="sr-only">Search all sessions</span>
            <SearchIcon
              aria-hidden="true"
              className="pointer-events-none absolute left-3 size-4 text-content-muted"
            />
            <input
              ref={searchRef}
              type="search"
              value={query}
              placeholder="Search sessions"
              className="h-[39px] w-full rounded-[9px] border border-line bg-surface-raised pr-3 pl-9 text-sm text-content-primary outline-none placeholder:text-content-quiet focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)]"
              onChange={(event) => setQuery(event.currentTarget.value)}
            />
          </label>
          <div className="overflow-y-auto border-t border-line p-2">
            {isLoadingAllSessions ? (
              <p
                aria-live="polite"
                className="px-3 py-2 text-[11px] text-content-muted"
              >
                Loading remaining sessions…
              </p>
            ) : null}
            {matches.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-content-muted">
                No sessions match this search.
              </p>
            ) : (
              matches.map((session) => (
                <SessionRow
                  key={`${session.player_id}:${session.id}`}
                  session={session}
                  onSelect={(selected) => {
                    onSelect(selected)
                    setOpen(false)
                  }}
                />
              ))
            )}
          </div>
        </ModalPopup>
      </ModalPortal>
    </Modal>
  )
}

function ResultNotice({
  result,
  onRefresh,
}: {
  result: SessionCatalogResult
  onRefresh: () => Promise<void>
}) {
  if (result.status === "loading") {
    return <p className="p-4 text-sm text-content-muted">Loading sessions…</p>
  }
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
  if (result.status === "reconnecting" && result.data === undefined) {
    return (
      <p className="p-4 text-sm text-warning">
        Reconnecting to the session catalog…
      </p>
    )
  }
  return null
}

function SessionSelector({
  catalogResult,
  isLoadingAllSessions,
  loadAllSessions,
  onRefresh,
  onSelect,
  onSelectPlayer,
  playerComplete,
  selected,
}: SessionSelectorProps) {
  const [contextOpen, setContextOpen] = useState(false)
  const catalog =
    catalogResult.status === "loading" || catalogResult.status === "error"
      ? undefined
      : catalogResult.data
  const latest = catalog === undefined ? [] : latestSessions(catalog, selected)
  const lifecycle = selected === null ? "idle" : sessionLifecycle(selected)
  const catalogState =
    catalogResult.status === "partial"
      ? catalogResult.completeness
      : catalogResult.status
  const selectAndClose = (session: SessionCatalogItem) => {
    onSelect(session)
    setContextOpen(false)
  }

  return (
    <Popover open={contextOpen} onOpenChange={setContextOpen}>
      <PopoverTrigger
        aria-label={
          selected === null
            ? "Select player and session"
            : [
                "Selected context",
                selected.character || selected.player_id,
                lifecycle,
                selected.id,
              ].join(", ")
        }
        className="flex h-[34px] max-w-[360px] min-w-0 items-center gap-2 rounded-[11px] border border-line bg-surface-raised px-3 text-left text-content-muted outline-none hover:border-line-strong focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)] max-[700px]:max-w-full"
      >
        <TelescopeIcon aria-hidden="true" className="size-3.5 flex-none" />
        {selected === null ? (
          <span className="truncate text-xs">Select context</span>
        ) : (
          <>
            <strong className="max-w-[140px] truncate text-[13px] font-medium text-content-primary">
              {selected.character || selected.player_id}
            </strong>
            <span aria-hidden="true">·</span>
            <span className="text-[11px] text-content-muted">{lifecycle}</span>
            <span aria-hidden="true">·</span>
            <span className="truncate font-mono text-[10px]">
              {shortSessionId(selected.id)}
            </span>
          </>
        )}
        <ChevronDownIcon
          aria-hidden="true"
          className="ml-auto size-3.5 flex-none"
        />
      </PopoverTrigger>
      <PopoverContent
        aria-label="Player and session context"
        align="end"
        sideOffset={7}
        className="w-[min(420px,calc(100vw-2rem))] gap-0 overflow-hidden rounded-[14px] border border-line-strong bg-surface p-0 shadow-popover ring-0"
      >
        {catalog === undefined ? (
          <ResultNotice result={catalogResult} onRefresh={onRefresh} />
        ) : (
          <>
            <section className="p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-[9.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase">
                  Selected context
                </p>
                <span className="text-[9px] text-content-quiet">
                  {catalogState}
                </span>
              </div>
              {selected === null ? (
                <p className="py-3 text-sm text-content-muted">
                  No session is available.
                </p>
              ) : (
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-1 py-1">
                  <SessionSummary session={selected} />
                  <p className="col-span-2 mt-1 text-[10px] text-content-muted">
                    {selected.control_available
                      ? `Control available: ${selected.control_state ?? "ready"}`
                      : "Read-only session"}
                  </p>
                </div>
              )}
            </section>
            {catalog.players.length > 1 ? (
              <label className="flex items-center gap-3 border-t border-line px-4 py-3 text-[10px] text-content-muted">
                <span>Player</span>
                <select
                  aria-label="Selected player"
                  value={selected?.player_id ?? ""}
                  className="min-w-0 flex-1 rounded-[8px] border border-line bg-surface-raised px-2 py-1.5 text-[11px] text-content-primary outline-none focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)]"
                  onChange={(event) =>
                    onSelectPlayer(event.currentTarget.value)
                  }
                >
                  {selected === null ? (
                    <option value="">Select player</option>
                  ) : null}
                  {catalog.players.map((player) => (
                    <option key={player.id} value={player.id}>
                      {player.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {latest.length > 0 ? (
              <section className="border-t border-line p-3">
                <p className="mb-1 px-2 text-[9.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase">
                  Latest five
                </p>
                {latest.map((session) => (
                  <SessionRow
                    key={`${session.player_id}:${session.id}`}
                    session={session}
                    onSelect={selectAndClose}
                  />
                ))}
              </section>
            ) : null}
            <div className="flex items-center border-t border-line">
              <div className="min-w-0 flex-1">
                <AllSessionsDialog
                  catalog={catalog}
                  isLoadingAllSessions={isLoadingAllSessions}
                  loadAllSessions={loadAllSessions}
                  onSelect={selectAndClose}
                  playerComplete={playerComplete}
                />
              </div>
              <button
                type="button"
                aria-label="Refresh session catalog"
                className="grid size-10 flex-none place-items-center border-l border-line text-content-muted outline-none hover:bg-surface-raised hover:text-content-primary focus-visible:[box-shadow:inset_0_0_0_2px_var(--accent)]"
                onClick={() => void onRefresh()}
              >
                <RefreshCwIcon aria-hidden="true" className="size-3.5" />
              </button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

export { SessionSelector, type SessionSelectorProps }
