import type { Meta, StoryObj } from "@storybook/react-vite"
import { ChevronDownIcon, MoreHorizontalIcon } from "lucide-react"
import { expect, userEvent, within } from "storybook/test"

import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { IconButton } from "@/components/ui/icon-button"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

const meta = {
  title: "Primitives/Disclosure and overlays",
  component: Dialog,
  tags: ["autodocs"],
} satisfies Meta<typeof Dialog>

export default meta

type Story = StoryObj<typeof meta>

export const DialogStates: Story = {
  render: () => (
    <Dialog defaultOpen>
      <DialogTrigger render={<Button />}>Open dialog</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Restart materialization?</DialogTitle>
          <DialogDescription>
            This workshop action changes no retained session.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter showCloseButton>
          <Button>Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
}

export const DialogClosedState: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger render={<Button />}>Open closed dialog</DialogTrigger>
      <DialogContent>
        <DialogTitle>Closed dialog contract</DialogTitle>
        <DialogDescription>
          The dialog remains absent until its trigger is activated.
        </DialogDescription>
      </DialogContent>
    </Dialog>
  ),
}

export const PopoverStates: Story = {
  render: () => (
    <Popover defaultOpen>
      <PopoverTrigger render={<Button variant="outline" />}>
        Open popover
      </PopoverTrigger>
      <PopoverContent>
        <PopoverHeader>
          <PopoverTitle>Composite cursor</PopoverTitle>
          <PopoverDescription>
            The opaque cursor covers every governed partition.
          </PopoverDescription>
        </PopoverHeader>
      </PopoverContent>
    </Popover>
  ),
}

export const PopoverClosedState: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger render={<Button variant="outline" />}>
        Open closed popover
      </PopoverTrigger>
      <PopoverContent>
        <PopoverTitle>Closed popover contract</PopoverTitle>
        <PopoverDescription>
          The popup remains absent until activation.
        </PopoverDescription>
      </PopoverContent>
    </Popover>
  ),
}

export const DropdownMenuStates: Story = {
  render: () => (
    <DropdownMenu defaultOpen>
      <DropdownMenuTrigger
        render={
          <IconButton variant="outline" aria-label="Session actions">
            <MoreHorizontalIcon aria-hidden="true" />
          </IconButton>
        }
      />
      <DropdownMenuContent>
        <DropdownMenuGroup>
          <DropdownMenuLabel>Session</DropdownMenuLabel>
          <DropdownMenuItem>
            Inspect
            <DropdownMenuShortcut>Enter</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuCheckboxItem checked>
            Follow updates
          </DropdownMenuCheckboxItem>
          <DropdownMenuItem disabled>Unavailable action</DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value="compact">
          <DropdownMenuRadioItem value="compact">Compact</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="comfortable">
            Comfortable
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>More</DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuItem variant="destructive">
              Remove local view
            </DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuContent>
    </DropdownMenu>
  ),
}

export const DropdownMenuClosedState: Story = {
  render: () => (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline">Closed menu</Button>}
      />
      <DropdownMenuContent>
        <DropdownMenuItem>Inspect</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  ),
}

export const DropdownMenuHoverState: Story = {
  render: () => (
    <DropdownMenu defaultOpen>
      <DropdownMenuTrigger render={<Button variant="outline" />}>
        Hover menu
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem>Hovered item</DropdownMenuItem>
        <DropdownMenuItem>Resting item</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  ),
  play: async ({ canvasElement }) => {
    const body = within(canvasElement.ownerDocument.body)
    const item = await body.findByRole("menuitem", { name: "Hovered item" })
    await userEvent.hover(item)
    await expect(item).toHaveAttribute("data-highlighted")
  },
}

export const SelectStates: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3">
      <Select defaultOpen defaultValue="running">
        <SelectTrigger aria-label="Lifecycle filter">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Lifecycle</SelectLabel>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="succeeded">Succeeded</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select disabled>
        <SelectTrigger aria-label="Disabled lifecycle filter">
          <SelectValue placeholder="Unavailable" />
        </SelectTrigger>
      </Select>
      <Select defaultValue="dense">
        <SelectTrigger size="sm" aria-label="Density">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="dense">Dense</SelectItem>
          <SelectItem value="normal">Normal</SelectItem>
        </SelectContent>
      </Select>
    </div>
  ),
}

export const SelectClosedState: Story = {
  render: () => (
    <Select defaultValue="running">
      <SelectTrigger aria-label="Closed lifecycle filter">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="running">Running</SelectItem>
        <SelectItem value="failed">Failed</SelectItem>
      </SelectContent>
    </Select>
  ),
}

export const SelectFocusState: Story = {
  render: () => (
    <Select defaultValue="running">
      <SelectTrigger aria-label="Focused lifecycle filter">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="running">Running</SelectItem>
      </SelectContent>
    </Select>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("combobox", { name: "Focused lifecycle filter" })
    ).toHaveFocus()
  },
}

export const SelectErrorState: Story = {
  render: () => (
    <Select defaultValue="failed">
      <SelectTrigger aria-label="Invalid lifecycle filter" aria-invalid="true">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="failed">Failed</SelectItem>
      </SelectContent>
    </Select>
  ),
}

export const TooltipStates: Story = {
  render: () => (
    <TooltipProvider>
      <Tooltip defaultOpen>
        <TooltipTrigger render={<Button variant="outline" />}>
          Focus or hover
        </TooltipTrigger>
        <TooltipContent>Open session detail</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ),
}

export const TooltipClosedState: Story = {
  render: () => (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger render={<Button variant="outline" />}>
          Closed tooltip
        </TooltipTrigger>
        <TooltipContent>Closed supporting context</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ),
}

export const TooltipFocusState: Story = {
  render: () => (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger render={<Button variant="outline" />}>
          Keyboard tooltip
        </TooltipTrigger>
        <TooltipContent>Keyboard supporting context</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ),
  play: async ({ canvasElement }) => {
    const body = within(canvasElement.ownerDocument.body)
    await userEvent.tab()
    await expect(
      body.getByRole("button", { name: "Keyboard tooltip" })
    ).toHaveFocus()
    const tooltip = await body.findByRole("tooltip", {
      name: "Keyboard supporting context",
    })
    await expect(tooltip).toBeVisible()
  },
}

export const CollapsibleStates: Story = {
  render: () => (
    <Collapsible
      defaultOpen
      className="max-w-md rounded-lg border border-line bg-surface p-3"
    >
      <CollapsibleTrigger
        render={<Button variant="ghost" className="w-full justify-between" />}
      >
        Materialization details
        <ChevronDownIcon aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-2 pt-3 text-sm text-content-muted">
        The panel remains keyboard reachable and reports its expanded state.
      </CollapsibleContent>
    </Collapsible>
  ),
}

export const CollapsibleClosedState: Story = {
  render: () => (
    <Collapsible className="max-w-md rounded-lg border border-line bg-surface p-3">
      <CollapsibleTrigger
        render={<Button variant="ghost" className="w-full justify-between" />}
      >
        Closed materialization details
        <ChevronDownIcon aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-2 pt-3 text-sm text-content-muted">
        Closed content.
      </CollapsibleContent>
    </Collapsible>
  ),
}
