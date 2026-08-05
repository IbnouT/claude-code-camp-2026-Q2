import { Outlet, useNavigate, useRouterState } from "@tanstack/react-router"
import { useEffect, useRef, type ReactNode } from "react"

import { MessageSquareTextIcon, SearchIcon } from "lucide-react"

import { ApplicationHeader } from "@/app/application-header"
import { useLiveActions } from "@/app/live-actions-context"
import { cn } from "@/lib/utils"
import { ThemeControl } from "@/app/theme-control"
import { selectedSession } from "@/app/session-context-model"
import {
  useSessionCatalog,
  useSessionCatalogLiveness,
} from "@/data/session-catalog"

type AppShellProps = {
  navigation: ReactNode
}

function AppShell({ navigation }: AppShellProps) {
  useSessionCatalogLiveness()
  const liveDialogs = useLiveActions()
  const contentRef = useRef<HTMLElement>(null)
  const location = useRouterState({
    select: (state) => state.location,
  })
  const navigate = useNavigate()
  const pathname = location.pathname
  const isReviewRoute = pathname === "/review"
  // The launcher is a full-bleed scene: no header, the theme control floats
  // top right.
  const isLauncherRoute = pathname === "/"
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

  const headerActionClassName =
    "inline-flex h-[34px] items-center justify-center gap-[7px] rounded-[11px] border border-line bg-surface-raised px-[13px] py-2 text-[12.5px] whitespace-nowrap outline-none hover:border-line-strong hover:bg-surface-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-[0.56] max-[1440px]:[&>span]:hidden"
  const askAction = (
    <button
      type="button"
      data-header-action="ask"
      aria-label="Ask about this session"
      className={cn(
        headerActionClassName,
        "text-content-muted max-[1440px]:px-2.5"
      )}
      disabled={selected === null}
      title="Ask about this session"
      onClick={liveDialogs.openAsk}
    >
      <SearchIcon aria-hidden="true" className="size-3.5" />
      <span>Ask about this session</span>
      <kbd className="rounded-[5px] border border-line-strong bg-surface px-[5px] py-0.5 font-mono text-[9px] text-content-quiet">
        ⌘K
      </kbd>
    </button>
  )
  const liveActions = (
    <>
      <button
        type="button"
        data-header-action="message"
        aria-label="Message agent"
        className={cn(
          headerActionClassName,
          "border-[color-mix(in_srgb,var(--warning)_34%,var(--line))] text-warning"
        )}
        disabled={selected?.control_available !== true}
        title={
          selected?.control_available
            ? "Guide the running agent"
            : "Messaging requires a running, controllable session"
        }
        onClick={liveDialogs.openMessage}
      >
        <MessageSquareTextIcon aria-hidden="true" className="size-3.5" />
        <span>Message agent</span>
      </button>
      {askAction}
    </>
  )
  const isSessionsRoute =
    pathname === "/sessions" || pathname.startsWith("/sessions/")
  const actions =
    pathname === "/live" ? liveActions : isSessionsRoute ? askAction : null

  return (
    <div
      data-testid="application-shell"
      className="relative min-h-svh bg-canvas text-content-primary"
    >
      <div className="flex min-h-svh w-full flex-col">
        {isLauncherRoute ? (
          <div className="absolute top-4 right-4 z-10">
            <ThemeControl />
          </div>
        ) : null}
        {isReviewRoute || isLauncherRoute ? null : (
          <ApplicationHeader
            onLeaveLive={
              pathname === "/live"
                ? () => {
                    void navigate({
                      to: "/",
                      search: { player: selected?.player_id },
                    })
                  }
                : undefined
            }
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
            isReviewRoute || isLauncherRoute
              ? "min-w-0 flex-1 outline-none"
              : pathname === "/live"
                ? "flex min-h-0 min-w-0 flex-1 flex-col outline-none"
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
