import { SearchIcon, XIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import {
  askQuestion,
  type AskResponseOutput,
  type QueryScope,
} from "@/data/ask"

type AskDialogProps = {
  open: boolean
  onClose: () => void
  playerId: string
  sessionId: string
  space?: "live" | "sessions"
  runId?: string
  selectedRecordId?: string | null
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError"
}

/**
 * Evidence questions over the retained session. Answers cite retained
 * records only, model use stays off.
 */
function AskDialog({
  open,
  onClose,
  playerId,
  sessionId,
  space = "live",
  runId,
  selectedRecordId = null,
}: AskDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [question, setQuestion] = useState("")
  const [limitToSelection, setLimitToSelection] = useState(false)
  const [answer, setAnswer] = useState<AskResponseOutput | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setQuestion("")
      setAnswer(null)
      setError("")
      setLimitToSelection(false)
      inputRef.current?.focus()
      return
    }
    abortRef.current?.abort()
  }, [open])
  useEffect(() => {
    abortRef.current?.abort()
  }, [sessionId])
  useEffect(() => () => abortRef.current?.abort(), [])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = question.trim()
    if (trimmed === "" || loading) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setAnswer(null)
    setError("")
    const scope: QueryScope = {
      space,
      player_id: playerId,
      ...(space === "sessions"
        ? { run_id: runId ?? sessionId }
        : { live_session_id: sessionId }),
      ...(limitToSelection && selectedRecordId !== null
        ? { selected_record_id: selectedRecordId }
        : {}),
    }
    try {
      setAnswer(await askQuestion(trimmed, scope, controller.signal))
    } catch (reason) {
      if (isAbortError(reason)) return
      setError(reason instanceof Error ? reason.message : "Ask failed")
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent
        showCloseButton={false}
        retained
        overlayClassName="supports-backdrop-filter:backdrop-blur-[8px]"
        className="top-[min(12vh,110px)] block max-h-[calc(100vh-min(12vh,110px)-16px)] w-[min(760px,calc(100%-32px))] translate-y-0 gap-0 overflow-y-auto p-0 leading-[normal] text-content-primary"
      >
        <DialogTitle className="sr-only">Ask about this session</DialogTitle>
        <form
          className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-2.5 border-b border-line p-4"
          onSubmit={submit}
        >
          <SearchIcon aria-hidden="true" className="size-[18px] text-accent" />
          <input
            ref={inputRef}
            aria-label="Question about this session"
            placeholder="Ask why, find a trace, or search exact evidence"
            value={question}
            className="min-w-0 rounded-[9px] border border-line bg-surface-raised px-3 py-2.5 text-content-primary outline-none focus:border-accent"
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button
            type="submit"
            disabled={question.trim() === "" || loading}
            className="h-[38px] rounded-[9px] border border-[rgb(104_225_220/25%)] bg-accent-soft px-[15px] font-semibold text-accent disabled:cursor-not-allowed disabled:opacity-55"
          >
            {loading ? "Planning…" : "Ask"}
          </button>
          <button
            type="button"
            aria-label="Close Ask"
            className="grid size-[34px] flex-none place-items-center rounded-[11px] border border-line bg-surface-raised text-content-muted outline-none hover:border-line-strong hover:bg-surface-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" className="size-4" />
          </button>
        </form>
        <div className="grid gap-[5px] p-4">
          <span className="text-[10px] tracking-[0.12em] text-content-quiet uppercase">
            Scope
          </span>
          <strong className="truncate text-[12px] text-content-primary">
            {playerId} · {sessionId}
          </strong>
          <small className="text-[10px] text-content-quiet">
            {limitToSelection && selectedRecordId !== null
              ? `Evidence through ${selectedRecordId}.`
              : "Whole session evidence."}{" "}
            Answers cite retained records. Model use is off.
          </small>
          <small className="text-[10px] text-content-quiet">
            Try: “Why did it stop?”, “Find the north gate”, or “Which positions
            were ambiguous?”
          </small>
          {selectedRecordId === null ? null : (
            <label className="mt-1.5 flex w-fit cursor-pointer items-center gap-2 text-[11px] text-content-muted">
              <input
                type="checkbox"
                checked={limitToSelection}
                className="accent-(--accent)"
                onChange={(event) => setLimitToSelection(event.target.checked)}
              />
              Limit the answer to evidence through {selectedRecordId}
            </label>
          )}
        </div>
        {error === "" ? null : (
          <p
            role="alert"
            className="m-0 border-t border-line p-4 leading-[1.55] text-danger"
          >
            {error}
          </p>
        )}
        {answer === null ? null : (
          <div className="grid gap-[5px] border-t border-line bg-surface-raised p-4">
            <small className="text-[10px] text-content-quiet">
              {answer.tier}
            </small>
            <p className="m-0 leading-[1.55]">{answer.answer}</p>
            {answer.missing.length > 0 ? (
              <p className="m-0 leading-[1.55] text-warning">
                Missing: {answer.missing.join(", ")}
              </p>
            ) : null}
            <small className="text-[10px] text-content-quiet">
              {answer.citations.length} evidence citations
            </small>
            {answer.citations.length === 0 ? null : (
              <ul className="mt-[5px] grid list-none gap-[7px] p-0">
                {answer.citations.map((citation, index) => (
                  <li
                    key={
                      citation.id ?? `${citation.label ?? "evidence"}-${index}`
                    }
                    className="grid gap-0.5 rounded-[8px] border border-line bg-surface px-2.5 py-2"
                  >
                    <strong className="text-[11px] text-content-primary">
                      {citation.label ?? citation.id ?? "Evidence"}
                    </strong>
                    {citation.excerpt ? (
                      <span className="text-[11px] text-content-muted">
                        {citation.excerpt}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export { AskDialog, type AskDialogProps }
