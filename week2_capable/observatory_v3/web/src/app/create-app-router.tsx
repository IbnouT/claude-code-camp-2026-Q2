import {
  createRoute,
  createRootRoute,
  createRouter,
  redirect,
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
import {
  RouteErrorBoundary,
  RouteNotFoundBoundary,
  RoutePendingBoundary,
} from "@/app/route-boundaries"
import { RoutePlaceholder } from "@/app/route-placeholder"

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

const liveSearchSchema = z.object({
  ...contextSearchShape,
  view: z.enum(["overview", "activity"]).catch("overview").default("overview"),
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

const sessionSearchSchema = z.object(contextSearchShape)

const sessionParamsSchema = z.object({
  sessionId: z.string().regex(/^[a-z0-9][a-z0-9-]{2,63}$/),
})

const navigationClassName =
  "rounded-sm border px-3 py-2 text-sm font-medium outline-none transition-colors focus-visible:border-accent focus-visible:[box-shadow:var(--focus-ring)]"
const activeNavigationClassName =
  "border-action-border bg-accent-soft text-content-primary"
const inactiveNavigationClassName =
  "border-transparent text-content-muted hover:bg-surface-soft hover:text-content-primary"

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
    component: () => <AppShell navigation={navigation} />,
    notFoundComponent: RouteNotFoundBoundary,
  })

  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    beforeLoad: () => {
      throw redirect({ to: "/live", replace: true })
    },
  })

  const liveRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/live",
    validateSearch: liveSearchSchema,
    beforeLoad: options.prepareRoute,
    errorComponent: RouteErrorBoundary,
    pendingComponent: RoutePendingBoundary,
    component: function LiveRoute() {
      const { view } = liveRoute.useSearch()
      return <RoutePlaceholder title="Live" routeState={`view=${view}`} />
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
      return (
        <RoutePlaceholder
          title="Session"
          routeState={`sessionId=${sessionId}`}
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
      {development === undefined ? null : (
        <rootRoute.Link
          to={development.to}
          activeOptions={{ exact: true, includeSearch: false }}
          className={navigationClassName}
          activeProps={{ className: activeNavigationClassName }}
          inactiveProps={{ className: inactiveNavigationClassName }}
        >
          {development.label}
        </rootRoute.Link>
      )}
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
