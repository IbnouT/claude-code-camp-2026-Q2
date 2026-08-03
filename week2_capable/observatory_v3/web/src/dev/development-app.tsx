import {
  createRoute,
  RouterProvider,
  type AnyRootRoute,
} from "@tanstack/react-router"

import {
  createAppRouter,
  type DevelopmentRouteExtension,
} from "@/app/create-app-router"
import { capabilitiesQueryOptions } from "@/data/capabilities"
import {
  ServerStateProvider,
  createServerStateClient,
} from "@/data/server-state-provider"
import { App as FoundationReview } from "@/dev/foundation-review"
import { ServerStateReview } from "@/dev/server-state-review"

const DEVELOPMENT_ROUTE_MARKER = "V3_DEVELOPMENT_ROUTER_REVIEW_ONLY"
const serverStateClient = createServerStateClient()

function DevelopmentReview() {
  return (
    <>
      <FoundationReview />
      <ServerStateReview />
    </>
  )
}

declare global {
  interface Window {
    observatoryDevelopmentRouter?: ReturnType<typeof createAppRouter>
    observatoryRoutePreparation?: {
      promise: Promise<void>
      resolve: () => void
    }
  }
}

function createDevelopmentRoute(
  rootRoute: AnyRootRoute
): DevelopmentRouteExtension {
  const route = createRoute({
    beforeLoad: () =>
      serverStateClient.prefetchQuery(capabilitiesQueryOptions()),
    getParentRoute: () => rootRoute,
    path: "/review",
    component: DevelopmentReview,
  })

  return {
    route,
    label: "Review",
    to: "/review",
  }
}

function prepareRoute() {
  return window.observatoryRoutePreparation?.promise
}

const router = createAppRouter({ createDevelopmentRoute, prepareRoute })
window.observatoryDevelopmentRouter = router

function App() {
  return (
    <>
      <span hidden>{DEVELOPMENT_ROUTE_MARKER}</span>
      <ServerStateProvider client={serverStateClient}>
        <RouterProvider router={router} />
      </ServerStateProvider>
    </>
  )
}

export { App, router }
