import { RouterProvider } from "@tanstack/react-router"

import { createAppRouter } from "@/app/create-app-router"
import {
  ServerStateProvider,
  createServerStateClient,
} from "@/data/server-state-provider"

const router = createAppRouter()
const serverStateClient = createServerStateClient()

function App() {
  return (
    <ServerStateProvider client={serverStateClient}>
      <RouterProvider router={router} />
    </ServerStateProvider>
  )
}

export { App, router }
