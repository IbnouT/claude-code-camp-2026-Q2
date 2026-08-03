import { RouterProvider } from "@tanstack/react-router"

import { createAppRouter } from "@/app/create-app-router"

const router = createAppRouter()

function App() {
  return <RouterProvider router={router} />
}

export { App, router }
