import type { VariantProps } from "class-variance-authority"

import {
  Button,
  buttonVariants,
  type ButtonProps,
} from "@/components/ui/button"
import { cn } from "@/lib/utils"

type IconButtonProps = Omit<ButtonProps, "aria-label" | "size"> &
  Pick<VariantProps<typeof buttonVariants>, "size"> & {
    "aria-label": string
  }

function IconButton({
  className,
  size = "icon",
  variant = "outline",
  children,
  ...props
}: IconButtonProps) {
  return (
    <Button
      data-slot="icon-button"
      size={size}
      variant={variant}
      className={cn(
        "gap-[7px] border-line bg-surface-raised px-1.5 py-px text-sm leading-[normal] font-normal text-accent transition-all duration-0 ease-[ease] hover:border-line-strong hover:bg-surface-soft",
        className
      )}
      {...props}
    >
      {children}
    </Button>
  )
}

export { IconButton, type IconButtonProps }
