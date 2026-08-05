import { useNavigate } from "@tanstack/react-router"
import { Clock3Icon, SearchIcon } from "lucide-react"
import { useMemo, useState } from "react"

import {
  useSessionCatalog,
  type SessionCatalogItem,
} from "@/data/session-catalog"
import { cn } from "@/lib/utils"

type SessionsListScreenProps = {
  playerId: string | undefined
}

function shortId(sessionId: string): string {
  return sessionId.length > 8 ? sessionId.slice(0, 8) : sessionId
}

function when(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "time unavailable"
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date)
}

function matches(session: SessionCatalogItem, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (normalized === "") return true
  return [
    session.id,
    session.state,
    session.objective ?? "",
    session.created_at,
    session.updated_at,
  ]
    .join(" ")
    .toLowerCase()
    .includes(normalized)
}

/**
 * Every retained session for the selected player, searchable, newest
 * first. A row opens the session's recorded story.
 */
function SessionsListScreen({ playerId }: SessionsListScreenProps) {
  const catalog = useSessionCatalog({ playerId })
  const navigate = useNavigate()
  const [search, setSearch] = useState("")

  const data =
    catalog.result.status === "loading" || catalog.result.status === "error"
      ? undefined
      : catalog.result.data
  const sessions = useMemo(() => {
    const scoped = (data?.sessions ?? []).filter(
      (session) => playerId === undefined || session.player_id === playerId
    )
    return [...scoped].sort(
      (left, right) =>
        Date.parse(right.updated_at) - Date.parse(left.updated_at)
    )
  }, [data?.sessions, playerId])
  const results = sessions.filter((session) => matches(session, search))

  return (
    <main className="mx-auto w-[min(880px,calc(100%-48px))] py-7">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="m-0 text-[18px] font-bold text-content-primary">
            Find a session
          </h1>
          <small className="text-content-muted">
            {sessions.length} session{sessions.length === 1 ? "" : "s"}
            {playerId === undefined ? "" : " for this player"}
          </small>
        </div>
      </header>
      <label className="mt-4 mb-2.5 flex items-center gap-[9px] rounded-[10px] border border-line-strong bg-canvas px-3 py-2.5 text-content-quiet">
        <SearchIcon aria-hidden="true" className="size-4" />
        <input
          aria-label="Search sessions"
          type="search"
          placeholder="Search by goal, state, date, or session id"
          value={search}
          className="min-w-0 flex-1 border-0 bg-transparent text-content-primary outline-none"
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <div className="grid gap-0.5">
        {results.length === 0 ? (
          <p className="p-9 text-center text-content-muted">
            No session matches “{search}”.
          </p>
        ) : (
          results.map((session) => (
            <button
              key={session.id}
              type="button"
              className="grid w-full cursor-pointer grid-cols-[10px_minmax(0,1fr)_auto] items-center gap-2.5 rounded-[9px] border border-transparent px-[9px] py-2.5 text-left text-content-primary hover:border-line hover:bg-surface-soft"
              onClick={() =>
                void navigate({
                  to: "/sessions/$sessionId",
                  params: { sessionId: session.id },
                  search: { view: "story" },
                })
              }
            >
              <span
                aria-hidden="true"
                className={cn(
                  "inline-block size-2 rounded-full bg-content-quiet",
                  session.live &&
                    "bg-accent shadow-[0_0_10px_rgb(104_225_220/55%)]"
                )}
              />
              <span className="min-w-0">
                <strong className="block truncate">
                  {session.objective?.trim() || "Goal not retained"}
                </strong>
                <small className="mt-0.5 block truncate text-[11px] text-content-muted">
                  {session.state} · {shortId(session.id)} ·{" "}
                  {when(session.updated_at)}
                </small>
              </span>
              <Clock3Icon
                aria-hidden="true"
                className="size-3.5 text-content-quiet"
              />
            </button>
          ))
        )}
      </div>
    </main>
  )
}

export { SessionsListScreen, type SessionsListScreenProps }
