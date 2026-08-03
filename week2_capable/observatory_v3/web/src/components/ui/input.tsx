import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const inputVariants = cva(
  "w-full min-w-0 rounded-[9px] border border-line bg-surface-raised text-sm leading-[normal] font-normal text-content-primary transition-all duration-0 ease-[ease] outline-none file:inline-flex file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-accent disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
  {
    variants: {
      density: {
        default: "h-[39px] px-3 py-2.5",
        dense: "h-7 px-2 py-0.5 text-sm",
      },
    },
    defaultVariants: {
      density: "default",
    },
  }
)

type InputProps = React.ComponentProps<"input"> &
  VariantProps<typeof inputVariants>

function Input({ className, type, density = "default", ...props }: InputProps) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      data-density={density}
      className={cn(inputVariants({ density }), className)}
      {...props}
    />
  )
}

export { Input, inputVariants, type InputProps }
