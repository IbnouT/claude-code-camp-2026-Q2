import { cva, type VariantProps } from "class-variance-authority"
import type { ComponentProps } from "react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const statusBadgeVariants = cva(
  "h-[21px] gap-[normal] rounded-[7px] border-line bg-surface-soft px-[9px] py-[3px] text-[11px] leading-[normal] font-normal capitalize transition-all duration-0 ease-[ease] before:hidden in-data-[theme=light]:text-content-primary",
  {
    variants: {
      status: {
        idle: "text-content-primary",
        checking: "text-lifecycle-checking",
        running: "text-lifecycle-running",
        succeeded: "text-lifecycle-succeeded",
        stopped: "text-content-primary",
        failed: "text-lifecycle-failed",
      },
    },
    defaultVariants: {
      status: "idle",
    },
  }
)

type StatusBadgeProps = Omit<ComponentProps<typeof Badge>, "variant"> &
  VariantProps<typeof statusBadgeVariants>

function StatusBadge({
  className,
  status = "idle",
  ...props
}: StatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      data-slot="status-badge"
      data-status={status}
      className={cn(statusBadgeVariants({ status }), className)}
      {...props}
    />
  )
}

export { StatusBadge, statusBadgeVariants, type StatusBadgeProps }
