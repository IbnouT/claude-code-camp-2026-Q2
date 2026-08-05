/**
 * Previous data may stand in during a refetch only while it belongs to
 * the same session. Switching player or session renders the loading
 * state, never another session's retained data.
 */
function sameSessionPlaceholder(sessionId: string | undefined) {
  return <TData,>(
    previousData: TData | undefined,
    previousQuery: { queryKey: readonly unknown[] } | undefined
  ): TData | undefined => {
    const scope = previousQuery?.queryKey[4]
    const previousSession =
      typeof scope === "object" && scope !== null && "sessionId" in scope
        ? (scope as { sessionId: string | null }).sessionId
        : null
    return previousSession === (sessionId ?? null) ? previousData : undefined
  }
}

export { sameSessionPlaceholder }
