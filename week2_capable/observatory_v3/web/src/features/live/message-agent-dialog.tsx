import { SendIcon, XIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import type { LiveJourney } from "@/data/live-view"
import { useOperatorMessage } from "@/data/message-command"
import { cn } from "@/lib/utils"

type OperatorMessage = LiveJourney["operator_messages"][number]

type MessageAgentDialogProps = {
  open: boolean
  onClose: () => void
  playerId: string
  sessionId: string
  sessionRunning: boolean
  controlAvailable: boolean
  objectiveAvailable: boolean
  followingLive: boolean
  selectedSequence: number | null
  messages: readonly OperatorMessage[]
}

/** Local send time, or the raw value when the date cannot be read. */
function sentTime(value: string): string {
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) return value
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed)
}

function appliedLine(message: OperatorMessage): string {
  if (message.applied_iteration === null) {
    return "waiting for the next iteration"
  }
  if (message.action === "revise") {
    return `replaced the goal at iteration ${message.applied_iteration}`
  }
  return `applied at iteration ${message.applied_iteration}`
}

type OptimisticEntry = {
  instruction: string
  sentAt: string
  baselineCount: number
}

/**
 * The operator message drawer: sent history, the instruction composer,
 * and the goal or nudge effect switch. Delivery is one durable command.
 */
function MessageAgentDialog({
  open,
  onClose,
  playerId,
  sessionId,
  sessionRunning,
  controlAvailable,
  objectiveAvailable,
  followingLive,
  selectedSequence,
  messages,
}: MessageAgentDialogProps) {
  const message = useOperatorMessage()
  const [action, setAction] = useState<"guide" | "revise">(
    objectiveAvailable ? "guide" : "revise"
  )
  const [instruction, setInstruction] = useState("")
  const [optimistic, setOptimistic] = useState<OptimisticEntry | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (optimistic !== null && messages.length > optimistic.baselineCount) {
      setOptimistic(null)
    }
  }, [messages.length, optimistic])
  const resetMessage = message.reset
  useEffect(() => {
    if (open) {
      setAction(objectiveAvailable ? "guide" : "revise")
      setInstruction("")
      setOptimistic(null)
      resetMessage()
      textareaRef.current?.focus()
    }
  }, [open, objectiveAvailable, resetMessage])

  const sending = message.isPending
  const canSend =
    followingLive && sessionRunning && controlAvailable && !sending
  const placeholder = !followingLive
    ? "Return to live to message the agent"
    : sessionRunning
      ? "Steer the agent"
      : "The agent is not running"

  const send = () => {
    const text = instruction.trim()
    if (text === "" || !canSend) return
    setOptimistic({
      instruction: text,
      sentAt: new Date().toISOString(),
      baselineCount: messages.length,
    })
    message.mutate(
      { session_id: sessionId, player_id: playerId, action, instruction: text },
      {
        onSuccess: () => {
          setInstruction("")
        },
        onError: () => {
          setOptimistic(null)
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent
        showCloseButton={false}
        aria-label="Your messages"
        overlayClassName="bg-[rgb(4_8_12/10%)] supports-backdrop-filter:backdrop-blur-none data-open:animate-[message-shade-in_360ms_ease-out_both] data-closed:animate-[message-shade-out_360ms_ease-in_both]"
        className="fixed inset-y-0 right-0 left-auto block h-full w-[min(430px,100%)] max-w-none translate-x-0 translate-y-0 gap-0 overflow-y-auto rounded-none border-y-0 border-r-0 border-l border-line-strong bg-[color-mix(in_srgb,var(--surface)_97%,transparent)] p-0 leading-[normal] shadow-[-18px_0_54px_rgb(0_0_0/28%)] ring-0 sm:max-w-none data-open:animate-[message-drawer-in_360ms_cubic-bezier(0.22,1,0.36,1)_both] data-closed:animate-[message-drawer-out_360ms_cubic-bezier(0.64,0,0.78,0)_both]"
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-[22px]">
          <div>
            <p className="mb-1.5 text-[10.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase">
              Running agent · {playerId}
            </p>
            <DialogTitle className="text-[20px] font-bold">
              Your messages
            </DialogTitle>
          </div>
          <button
            type="button"
            aria-label="Close messages"
            className="grid size-[38px] place-items-center rounded-[11px] border border-line bg-surface-raised text-content-muted outline-none hover:border-line-strong hover:bg-surface-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            onClick={onClose}
          >
            <XIcon aria-hidden="true" className="size-[17px]" />
          </button>
        </header>
        <div className="grid gap-3.5 px-[22px] pt-[18px] pb-6">
          <div
            aria-label="Sent message history"
            className="grid max-h-[min(44vh,420px)] gap-2.5 overflow-y-auto"
          >
            {messages.length === 0 && optimistic === null ? (
              <p className="rounded-[8px] border border-dashed border-line p-3.5 text-[11px] leading-normal text-content-quiet">
                You have not messaged this agent.
              </p>
            ) : (
              <>
                {messages.map((entry, index) => (
                  <article
                    key={`${entry.sent_at}-${index}`}
                    className="grid gap-1.5 rounded-[8px] border border-l-2 border-line border-l-warning bg-surface-raised px-[13px] py-3"
                  >
                    <p className="text-[12px] text-content-primary">
                      {entry.instruction}
                    </p>
                    <small className="text-[10px] text-content-quiet">
                      {sentTime(entry.sent_at)} · {appliedLine(entry)}
                    </small>
                  </article>
                ))}
                {optimistic === null ? null : (
                  <article className="grid gap-1.5 rounded-[8px] border border-l-2 border-line border-l-accent bg-surface-raised px-[13px] py-3">
                    <p className="text-[12px] text-content-primary">
                      {optimistic.instruction}
                    </p>
                    <small className="text-[10px] text-content-quiet">
                      {sentTime(optimistic.sentAt)} ·{" "}
                      {sending ? "sending…" : "waiting for the next iteration"}
                    </small>
                  </article>
                )}
              </>
            )}
          </div>
          <label
            htmlFor="live-agent-message"
            className="text-[12px] font-semibold text-content-primary"
          >
            Message for the agent
          </label>
          <textarea
            id="live-agent-message"
            ref={textareaRef}
            disabled={!followingLive || !sessionRunning}
            maxLength={4000}
            rows={5}
            placeholder={placeholder}
            value={instruction}
            className="min-h-[150px] resize-none rounded-[10px] border border-line bg-surface-raised p-3 text-content-primary outline-none focus:border-accent"
            onChange={(event) => setInstruction(event.target.value)}
          />
          {followingLive ? null : (
            <p className="text-[11px] leading-normal text-content-quiet">
              A message would arrive at the live boundary, not at the moment
              being inspected.
            </p>
          )}
          {sessionRunning ? null : (
            <p className="text-[11px] leading-normal text-content-quiet">
              The agent is not running.
            </p>
          )}
          {message.isError ? (
            <p role="alert" className="text-[11px] leading-normal text-danger">
              {message.error instanceof Error
                ? message.error.message
                : "Message failed"}
            </p>
          ) : null}
          <div className="flex items-center justify-between gap-3.5">
            {followingLive && sessionRunning ? (
              <div
                role="group"
                aria-label="Message effect"
                className="inline-flex items-center gap-[3px] rounded-[9px] border border-line bg-[color-mix(in_srgb,var(--canvas)_58%,transparent)] p-[3px] text-[11px] text-content-quiet"
              >
                <button
                  type="button"
                  aria-pressed={action === "revise"}
                  className={cn(
                    "min-h-8 min-w-[70px] rounded-[6px] px-3 py-[7px] font-semibold transition-colors hover:text-content-primary",
                    action === "revise" &&
                      "bg-[color-mix(in_srgb,var(--warning)_15%,var(--surface-raised))] text-warning"
                  )}
                  onClick={() => setAction("revise")}
                >
                  Goal
                </button>
                <button
                  type="button"
                  aria-pressed={action === "guide"}
                  className={cn(
                    "min-h-8 min-w-[70px] rounded-[6px] px-3 py-[7px] font-semibold transition-colors hover:text-content-primary",
                    action === "guide" &&
                      "bg-[color-mix(in_srgb,var(--warning)_15%,var(--surface-raised))] text-warning"
                  )}
                  onClick={() => setAction("guide")}
                >
                  Nudge
                </button>
              </div>
            ) : (
              <span className="font-mono text-[9px] text-content-quiet">
                {followingLive
                  ? "session stopped"
                  : `inspecting sequence ${selectedSequence ?? "unknown"}`}
              </span>
            )}
            <button
              type="button"
              aria-label="Send message"
              disabled={!canSend || instruction.trim() === ""}
              className="inline-flex items-center gap-[7px] rounded-[9px] border border-[color-mix(in_srgb,var(--warning)_38%,var(--line))] bg-[color-mix(in_srgb,var(--warning)_12%,var(--surface-raised))] px-[13px] py-[9px] text-warning outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50"
              onClick={send}
            >
              <SendIcon aria-hidden="true" className="size-[15px]" />
              {sending ? "Sending" : "Send"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export { MessageAgentDialog, type MessageAgentDialogProps }
