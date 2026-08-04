import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react"

type LiveActionsValue = {
  askOpen: boolean
  messageOpen: boolean
  openAsk: () => void
  openMessage: () => void
  closeAsk: () => void
  closeMessage: () => void
}

const LiveActionsContext = createContext<LiveActionsValue | null>(null)

/**
 * Shared open state for the Live dialogs: the header buttons open them,
 * the Live screen renders them.
 */
function LiveActionsProvider({ children }: { children: ReactNode }) {
  const [askOpen, setAskOpen] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const openAsk = useCallback(() => setAskOpen(true), [])
  const openMessage = useCallback(() => setMessageOpen(true), [])
  const closeAsk = useCallback(() => setAskOpen(false), [])
  const closeMessage = useCallback(() => setMessageOpen(false), [])
  const value = useMemo(
    () => ({
      askOpen,
      messageOpen,
      openAsk,
      openMessage,
      closeAsk,
      closeMessage,
    }),
    [askOpen, messageOpen, openAsk, openMessage, closeAsk, closeMessage]
  )
  return (
    <LiveActionsContext.Provider value={value}>
      {children}
    </LiveActionsContext.Provider>
  )
}

function useLiveActions(): LiveActionsValue {
  const value = useContext(LiveActionsContext)
  if (value === null) {
    throw new Error("useLiveActions requires LiveActionsProvider")
  }
  return value
}

export { LiveActionsProvider, useLiveActions }
