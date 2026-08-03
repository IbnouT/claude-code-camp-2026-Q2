type ResourceIdentity = {
  id: string
  kind: string
  playerId?: string | null
  sessionId?: string | null
}

type PageDimensions = {
  cursor: string | null
  limit: number
  parameters: Readonly<Record<string, number | string>>
  serverEpoch: string | null
}

type DetailDimensions = {
  serverEpoch: string | null
  sourceCursor: string | null
}

const queryKeys = {
  all: ["observatory"] as const,
  capabilities: () => ["observatory", "capabilities"] as const,
  resource: ({
    kind,
    id,
    playerId = null,
    sessionId = null,
  }: ResourceIdentity) =>
    ["observatory", "resource", kind, id, { playerId, sessionId }] as const,
  resourceDetail: (identity: ResourceIdentity, dimensions: DetailDimensions) =>
    [...queryKeys.resource(identity), "detail", dimensions] as const,
  resourcePage: (identity: ResourceIdentity, dimensions: PageDimensions) =>
    [...queryKeys.resource(identity), "page", dimensions] as const,
}

export {
  queryKeys,
  type DetailDimensions,
  type PageDimensions,
  type ResourceIdentity,
}
