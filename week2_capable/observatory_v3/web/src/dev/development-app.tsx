import {
  createRoute,
  RouterProvider,
  type AnyRootRoute,
} from "@tanstack/react-router"

import {
  createAppRouter,
  type DevelopmentRouteExtension,
} from "@/app/create-app-router"
import { App as FoundationReview } from "@/dev/foundation-review"

const DEVELOPMENT_ROUTE_MARKER = "V3_DEVELOPMENT_ROUTER_REVIEW_ONLY"

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
    getParentRoute: () => rootRoute,
    path: "/review",
    component: FoundationReview,
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
      <RouterProvider router={router} />
    </>
  )
}

export { App, router }
