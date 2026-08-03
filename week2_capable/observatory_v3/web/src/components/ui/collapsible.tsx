"use client"

import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

function Collapsible({ ...props }: CollapsiblePrimitive.Root.Props) {
  return <CollapsiblePrimitive.Root data-slot="collapsible" {...props} />
}

const collapsibleTriggerVariants = cva("", {
  variants: {
    variant: {
      plain: "",
      retained:
        "flex min-h-9 w-full items-center justify-between gap-3 border-0 [border-style:none] border-accent bg-transparent px-[11px] py-2 text-[9.5px] leading-[normal] font-semibold tracking-[0.12em] text-accent uppercase transition-all duration-0 ease-[ease] hover:bg-surface-raised hover:text-content-primary",
    },
  },
  defaultVariants: {
    variant: "plain",
  },
})

function CollapsibleTrigger({
  className,
  variant = "plain",
  ...props
}: CollapsiblePrimitive.Trigger.Props &
  VariantProps<typeof collapsibleTriggerVariants>) {
  return (
    <CollapsiblePrimitive.Trigger
      data-slot="collapsible-trigger"
      className={cn(collapsibleTriggerVariants({ variant }), className)}
      {...props}
    />
  )
}

function CollapsibleContent({ ...props }: CollapsiblePrimitive.Panel.Props) {
  return (
    <CollapsiblePrimitive.Panel data-slot="collapsible-content" {...props} />
  )
}

export {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
  collapsibleTriggerVariants,
}
