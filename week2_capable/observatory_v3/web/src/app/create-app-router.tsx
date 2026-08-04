import {
  createRoute,
  createRootRoute,
  createRouter,
  type AnyRootRoute,
  type AnyRoute,
} from "@tanstack/react-router"
import type { RouterHistory } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { z } from "zod"
import {
  ActivityIcon,
  BookOpenIcon,
  FlaskConicalIcon,
  TelescopeIcon,
} from "lucide-react"

import { AppShell } from "@/app/app-shell"
import { LiveActionsProvider } from "@/app/live-actions-context"
import { LiveRouteScreen } from "@/features/live/live-route-screen"
import {
  RouteErrorBoundary,
  RouteNotFoundBoundary,
  RoutePendingBoundary,
} from "@/app/route-boundaries"
import { RoutePlaceholder } from "@/app/route-placeholder"
import { Launcher } from "@/features/launcher/launcher"

type DevelopmentRouteExtension = {
  label: string
  route: AnyRoute
  to: string
}

type CreateAppRouterOptions = {
  createDevelopmentRoute?: (
    rootRoute: AnyRootRoute
  ) => DevelopmentRouteExtension
  history?: RouterHistory
  prepareRoute?: () => Promise<void> | void
}

const contextSearchShape = {
  player: z.string().max(120).optional().catch(undefined),
  session: z.string().max(200).optional().catch(undefined),
}

const indexSearchSchema = z.object({
  player: z.string().max(120).optional().catch(undefined),
  // The search parser reads ?load=1 as a number; accept both spellings.
  load: z
    .union([z.literal(1), z.literal("1")])
    .optional()
    .catch(undefined),
})

const liveSearchSchema = z.object({
  ...contextSearchShape,
  view: z.enum(["overview", "activity"]).catch("overview").default("overview"),
  through: z.number().int().positive().optional().catch(undefined),
  room: z.string().max(200).optional().catch(undefined),
})

const sessionsSearchSchema = z.object({
  ...contextSearchShape,
  page: z.coerce.number().int().positive().catch(1).default(1),
  state: z.enum(["all", "running", "complete"]).catch("all").default("all"),
})

const experimentsSearchSchema = z.object({
  ...contextSearchShape,
  lens: z.enum(["compare", "paths"]).catch("compare").default("compare"),
})

const knowledgeSearchSchema = z.object({
  ...contextSearchShape,
  query: z.string().max(120).catch("").default(""),
})

const sessionSearchSchema = z.object({
  ...contextSearchShape,
  view: z.enum(["story", "map", "cost"]).catch("story").default("story"),
})

const sessionParamsSchema = z.object({
  sessionId: z.string().regex(/^[a-z0-9][a-z0-9-]{2,63}$/),
})

const navigationClassName =
  "gap-[7px] rounded-[10px] border-0 px-3.5 py-2 text-center text-[13.5px] font-medium outline-none transition-colors focus-visible:[box-shadow:var(--focus-ring)]"
const activeNavigationClassName =
  "bg-accent-soft text-accent shadow-[inset_0_0_0_1px_rgb(104_225_220/18%)]"
const inactiveNavigationClassName =
  "text-content-muted hover:bg-surface-raised hover:text-content-primary"

function contextFromSearch(previous: Record<string, unknown>) {
  return {
    player: typeof previous.player === "string" ? previous.player : undefined,
    session:
      typeof previous.session === "string" ? previous.session : undefined,
  }
}

function createAppRouter(options: CreateAppRouterOptions = {}) {
  let navigation: ReactNode = null
  const rootRoute = createRootRoute({
    component: () => (
      <LiveActionsProvider>
        <AppShell navigation={navigation} />
      </LiveActionsProvider>
    ),
    notFoundComponent: RouteNotFoundBoundary,
  })

  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    validateSearch: indexSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    component: Launcher,
  })

  const liveRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/live",
    validateSearch: liveSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    component: function LiveRoute() {
      const { player, session, through, room } = liveRoute.useSearch()
      return (
        <LiveRouteScreen
          playerId={player}
          sessionId={session}
          through={through ?? null}
          room={room ?? null}
        />
      )
    },
  })

  const sessionsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/sessions",
    validateSearch: sessionsSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    component: function SessionsRoute() {
      const { page, state } = sessionsRoute.useSearch()
      return (
        <RoutePlaceholder
          title="Sessions"
          routeState={`state=${state};page=${page}`}
        />
      )
    },
  })

  const sessionRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/sessions/$sessionId",
    validateSearch: sessionSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    params: {
      parse: (params) => sessionParamsSchema.parse(params),
      stringify: (params) => params,
    },
    component: function SessionRoute() {
      const { sessionId } = sessionRoute.useParams()
      const { view } = sessionRoute.useSearch()
      return (
        <RoutePlaceholder
          title="Session"
          routeState={`sessionId=${sessionId};view=${view}`}
        />
      )
    },
  })

  const experimentsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/experiments",
    validateSearch: experimentsSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    component: function ExperimentsRoute() {
      const { lens } = experimentsRoute.useSearch()
      return (
        <RoutePlaceholder title="Experiments" routeState={`lens=${lens}`} />
      )
    },
  })

  const knowledgeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/knowledge",
    validateSearch: knowledgeSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    component: function KnowledgeRoute() {
      const { query } = knowledgeRoute.useSearch()
      return (
        <RoutePlaceholder
          title="Knowledge"
          routeState={`query=${query || "empty"}`}
        />
      )
    },
  })

  const development = options.createDevelopmentRoute?.(rootRoute)
  const children = [
    indexRoute,
    liveRoute,
    sessionsRoute,
    sessionRoute,
    experimentsRoute,
    knowledgeRoute,
    ...(development === undefined ? [] : [development.route]),
  ]

  navigation = (
    <>
      <rootRoute.Link
        aria-label="Live"
        to="/live"
        search={(previous: Record<string, unknown>) => ({
          ...contextFromSearch(previous),
          view: "overview",
        })}
        activeOptions={{ exact: true, includeSearch: false }}
        className={navigationClassName}
        activeProps={{ className: activeNavigationClassName }}
        inactiveProps={{ className: inactiveNavigationClassName }}
      >
        <ActivityIcon aria-hidden="true" className="size-[15px]" />
        <span>Live</span>
      </rootRoute.Link>
      <rootRoute.Link
        aria-label="Sessions"
        to="/sessions"
        search={(previous: Record<string, unknown>) => ({
          ...contextFromSearch(previous),
          page: 1,
          state: "all",
        })}
        activeOptions={{ exact: false, includeSearch: false }}
        className={navigationClassName}
        activeProps={{ className: activeNavigationClassName }}
        inactiveProps={{ className: inactiveNavigationClassName }}
      >
        <TelescopeIcon aria-hidden="true" className="size-[15px]" />
        <span>Sessions</span>
      </rootRoute.Link>
      <rootRoute.Link
        aria-label="Experiments"
        to="/experiments"
        search={(previous: Record<string, unknown>) => ({
          ...contextFromSearch(previous),
          lens: "compare",
        })}
        activeOptions={{ exact: true, includeSearch: false }}
        className={navigationClassName}
        activeProps={{ className: activeNavigationClassName }}
        inactiveProps={{ className: inactiveNavigationClassName }}
      >
        <FlaskConicalIcon aria-hidden="true" className="size-[15px]" />
        <span>Experiments</span>
      </rootRoute.Link>
      <rootRoute.Link
        aria-label="Knowledge"
        to="/knowledge"
        search={(previous: Record<string, unknown>) => ({
          ...contextFromSearch(previous),
          query: "",
        })}
        activeOptions={{ exact: true, includeSearch: false }}
        className={navigationClassName}
        activeProps={{ className: activeNavigationClassName }}
        inactiveProps={{ className: inactiveNavigationClassName }}
      >
        <BookOpenIcon aria-hidden="true" className="size-[15px]" />
        <span>Knowledge</span>
      </rootRoute.Link>
    </>
  )

  return createRouter({
    routeTree: rootRoute.addChildren(children),
    history: options.history,
    defaultPreload: "intent",
    defaultPendingMs: 150,
    defaultPendingMinMs: 250,
    notFoundMode: "root",
  })
}

type ObservatoryRouter = ReturnType<typeof createAppRouter>

declare module "@tanstack/react-router" {
  interface Register {
    router: ObservatoryRouter
  }
}

export {
  createAppRouter,
  activeNavigationClassName,
  inactiveNavigationClassName,
  navigationClassName,
  type CreateAppRouterOptions,
  type DevelopmentRouteExtension,
  type ObservatoryRouter,
}
