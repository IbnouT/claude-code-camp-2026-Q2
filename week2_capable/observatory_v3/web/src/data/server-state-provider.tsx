import { QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"

import { createObservatoryQueryClient } from "@/data/query-client"

type ServerStateProviderProps = {
  children: ReactNode
  client?: QueryClient
}

function createServerStateClient(): QueryClient {
  return createObservatoryQueryClient()
}

function ServerStateProvider({
  children,
  client: providedClient,
}: ServerStateProviderProps) {
  const [ownedClient] = useState(
    () => providedClient ?? createObservatoryQueryClient()
  )
  return (
    <QueryClientProvider client={ownedClient}>{children}</QueryClientProvider>
  )
}

export {
  ServerStateProvider,
  createServerStateClient,
  type ServerStateProviderProps,
}
