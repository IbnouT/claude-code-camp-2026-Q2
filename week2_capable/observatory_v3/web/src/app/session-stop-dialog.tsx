import { CircleStopIcon, ShieldAlertIcon } from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { StopFailedError, useStopCommand } from "@/data/stop-command"
import type { SessionCatalogItem } from "@/data/session-catalog"

type SessionStopDialogProps = {
  session: SessionCatalogItem
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * The stop confirmation: what stopping means, the bounded grace warning,
 * and a truthful inline failure that leaves the session state untouched.
 */
function SessionStopDialog({
  session,
  open,
  onOpenChange,
}: SessionStopDialogProps) {
  const stop = useStopCommand()

  const close = (next: boolean) => {
    if (stop.isPending) return
    if (!next) stop.reset()
    onOpenChange(next)
  }

  const confirm = () => {
    stop.mutate(
      {
        session_id: session.id,
        player_id: session.player_id,
      },
      {
        onSuccess: () => {
          onOpenChange(false)
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        className="max-w-[420px]"
        showCloseButton={!stop.isPending}
      >
        <DialogHeader>
          <p className="text-[9.5px] font-semibold tracking-[0.14em] text-content-quiet uppercase">
            Session lifecycle
          </p>
          <DialogTitle>Stop this session?</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2 rounded-[9px] border border-line bg-surface-soft px-3 py-2.5">
          <span className="grid gap-0.5">
            <small className="text-[9.5px] text-content-quiet">Player</small>
            <strong className="text-[12px] text-content-primary">
              {session.character || session.player_id}
            </strong>
          </span>
          <span className="grid min-w-0 gap-0.5">
            <small className="text-[9.5px] text-content-quiet">Session</small>
            <strong className="truncate font-mono text-[11px] text-content-primary">
              {session.id}
            </strong>
          </span>
        </div>
        <DialogDescription className="flex items-start gap-2.5 text-[12px] text-content-muted">
          <CircleStopIcon
            aria-hidden="true"
            className="mt-0.5 size-[19px] flex-none text-danger"
          />
          <span className="grid gap-0.5">
            <strong className="text-content-primary">
              The agent will leave the game.
            </strong>
            The recording is preserved and the character becomes available for
            another session after cleanup completes.
          </span>
        </DialogDescription>
        <p className="flex items-start gap-2.5 rounded-[9px] border border-[color-mix(in_srgb,var(--warning)_34%,var(--line))] bg-warning-soft px-3 py-2.5 text-[11px] text-content-muted">
          <ShieldAlertIcon
            aria-hidden="true"
            className="mt-0.5 size-[17px] flex-none text-warning"
          />
          A turn already in progress gets a bounded grace period. If it does not
          finish, only this verified session process group is stopped.
        </p>
        {stop.isError ? (
          <p
            role="alert"
            className="flex items-start gap-2.5 rounded-[9px] border border-[color-mix(in_srgb,var(--danger)_34%,var(--line))] bg-danger-soft px-3 py-2.5 text-[11px] text-content-muted"
          >
            <ShieldAlertIcon
              aria-hidden="true"
              className="mt-0.5 size-4 flex-none text-danger"
            />
            <span className="grid gap-0.5">
              <strong className="text-content-primary">
                Session is still running
              </strong>
              {stop.error instanceof StopFailedError
                ? stop.error.message
                : "The session could not be stopped."}
            </span>
          </p>
        ) : null}
        <DialogFooter>
          <button
            type="button"
            disabled={stop.isPending}
            className="rounded-[9px] border border-line px-3.5 py-2 text-[12px] text-content-primary outline-none hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-[0.56]"
            onClick={() => close(false)}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={stop.isPending}
            className="rounded-[9px] border border-[color-mix(in_srgb,var(--danger)_44%,var(--line))] bg-danger-soft px-3.5 py-2 text-[12px] font-medium text-danger outline-none hover:border-danger focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger disabled:cursor-not-allowed disabled:opacity-[0.56]"
            onClick={confirm}
          >
            {stop.isPending ? "Stopping…" : "Stop session"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export { SessionStopDialog, type SessionStopDialogProps }
