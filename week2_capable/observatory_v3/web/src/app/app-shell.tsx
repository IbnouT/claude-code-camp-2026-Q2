import {
  Link,
  Outlet,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router"
import { useEffect, useRef, type ReactNode } from "react"

import { ApplicationHeader } from "@/app/application-header"
import { selectedSession } from "@/app/session-context-model"
import { useSessionCatalog } from "@/data/session-catalog"

type AppShellProps = {
  navigation: ReactNode
}

function AppShell({ navigation }: AppShellProps) {
  const contentRef = useRef<HTMLElement>(null)
  const location = useRouterState({
    select: (state) => state.location,
  })
  const navigate = useNavigate()
  const pathname = location.pathname
  const isReviewRoute = pathname === "/review"
  const contextSearch =
    typeof location.search === "object" && location.search !== null
      ? (location.search as Record<string, unknown>)
      : {}
  const playerId =
    typeof contextSearch.player === "string" ? contextSearch.player : undefined
  const sessionId =
    typeof contextSearch.session === "string"
      ? contextSearch.session
      : undefined
  const detailSessionId = pathname.startsWith("/sessions/")
    ? pathname.slice("/sessions/".length)
    : undefined
  const sessionCatalog = useSessionCatalog({
    detailSessionId,
    playerId,
    sessionId,
  })
  const catalog =
    sessionCatalog.result.status === "loading" ||
    sessionCatalog.result.status === "error"
      ? undefined
      : sessionCatalog.result.data
  const selected =
    catalog === undefined || sessionCatalog.isResolvingIdentity
      ? null
      : selectedSession(catalog, {
          detailSessionId,
          playerId,
          sessionId,
        })

  useEffect(() => {
    contentRef.current?.focus()
  }, [pathname])

  useEffect(() => {
    if (selected === null || sessionCatalog.isResolvingIdentity) return
    if (playerId === selected.player_id && sessionId === selected.id) return

    void navigate({
      to: ".",
      replace: true,
      search: (previous: Record<string, unknown>) => ({
        ...previous,
        player: selected.player_id,
        session: selected.id,
      }),
    })
  }, [
    navigate,
    playerId,
    selected,
    sessionCatalog.isResolvingIdentity,
    sessionId,
  ])

  const selectContext = (session: NonNullable<typeof selected>) => {
    void navigate({
      to: ".",
      replace: true,
      search: (previous: Record<string, unknown>) => ({
        ...previous,
        player: session.player_id,
        session: session.id,
      }),
    })
  }

  const selectPlayer = (nextPlayerId: string) => {
    void navigate({
      to: ".",
      replace: true,
      search: (previous: Record<string, unknown>) => ({
        ...previous,
        player: nextPlayerId,
        session: undefined,
      }),
    })
  }

  const actions =
    selected === null ? null : selected.live ? (
      pathname === "/live" ? (
        <span className="rounded-[9px] border border-success/30 bg-success-soft px-2.5 py-2 text-[10px] text-content-primary">
          Live context
        </span>
      ) : (
        <Link
          to="/live"
          search={{
            player: selected.player_id,
            session: selected.id,
            view: "overview",
          }}
          className="rounded-[9px] border border-action-border px-3 py-2 text-[11px] font-medium text-accent outline-none hover:bg-accent-soft focus-visible:[box-shadow:var(--focus-ring)]"
        >
          Open Live
        </Link>
      )
    ) : pathname === `/sessions/${selected.id}` ? (
      <span className="rounded-[9px] border border-line bg-surface-soft px-2.5 py-2 text-[10px] text-content-muted">
        Recording selected
      </span>
    ) : (
      <Link
        to="/sessions/$sessionId"
        params={{ sessionId: selected.id }}
        search={{
          player: selected.player_id,
          session: selected.id,
        }}
        className="rounded-[9px] border border-line px-3 py-2 text-[11px] font-medium text-content-primary outline-none hover:bg-surface-soft focus-visible:[box-shadow:var(--focus-ring)]"
      >
        View recording
      </Link>
    )

  return (
    <div
      data-testid="application-shell"
      className="min-h-svh bg-canvas text-content-primary"
    >
      <div className="flex min-h-svh w-full flex-col">
        {isReviewRoute ? null : (
          <ApplicationHeader
            actions={actions}
            brandContext={{
              player: selected?.player_id,
              session: selected?.id,
            }}
            navigation={navigation}
            onSelect={selectContext}
            onSelectPlayer={selectPlayer}
            selected={selected}
            sessionCatalog={sessionCatalog}
          />
        )}
        {isReviewRoute ? (
          <aside className="border-b border-line bg-surface p-4">
            <div className="text-xs font-semibold tracking-[0.18em] text-accent uppercase">
              Boukensha Observatory
            </div>
            <nav
              aria-label="Observatory sections"
              className="mt-4 flex flex-wrap gap-2"
            >
              {navigation}
            </nav>
          </aside>
        ) : null}
        <main
          ref={contentRef}
          tabIndex={-1}
          data-testid="route-content"
          className={
            isReviewRoute
              ? "min-w-0 flex-1 outline-none"
              : "min-w-0 flex-1 p-5 outline-none sm:p-8"
          }
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export { AppShell, type AppShellProps }
