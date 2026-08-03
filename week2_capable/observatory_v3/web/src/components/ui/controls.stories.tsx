import type { Meta, StoryObj } from "@storybook/react-vite"
import { BellIcon, SearchIcon } from "lucide-react"
import { useState } from "react"
import { expect, userEvent, within } from "storybook/test"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { IconButton } from "@/components/ui/icon-button"
import { Input } from "@/components/ui/input"
import { SearchInput } from "@/components/ui/search-input"
import { StatusBadge } from "@/components/ui/status-badge"

const meta = {
  title: "Primitives/Controls and status",
  component: Button,
  tags: ["autodocs"],
} satisfies Meta<typeof Button>

export default meta

type Story = StoryObj<typeof meta>

export const ButtonStates: Story = {
  render: () => (
    <div className="grid max-w-3xl gap-5">
      <div className="flex flex-wrap gap-2">
        {(
          [
            "default",
            "secondary",
            "outline",
            "ghost",
            "destructive",
            "link",
          ] as const
        ).map((variant) => (
          <Button key={variant} variant={variant}>
            {variant}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {(["xs", "sm", "default", "lg"] as const).map((size) => (
          <Button key={size} size={size}>
            {size}
          </Button>
        ))}
        <Button disabled>Disabled</Button>
        <Button aria-invalid="true">Error</Button>
      </div>
    </div>
  ),
}

export const ButtonFocusState: Story = {
  render: () => <Button>Keyboard focus</Button>,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("button", { name: "Keyboard focus" })
    ).toHaveFocus()
  },
}

export const ButtonHoverState: Story = {
  render: () => <Button data-hovered="">Hover</Button>,
}

export const ButtonActiveState: Story = {
  render: () => <Button data-pressed="">Active</Button>,
}

export const ButtonDisabledState: Story = {
  render: () => <Button disabled>Disabled</Button>,
}

export const IconButtonStates: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-2">
      {(["icon-xs", "icon-sm", "icon", "icon-lg"] as const).map((size) => (
        <IconButton
          key={size}
          size={size}
          variant="outline"
          aria-label={`Notifications, ${size}`}
        >
          <BellIcon aria-hidden="true" />
        </IconButton>
      ))}
      <IconButton disabled aria-label="Notifications unavailable">
        <BellIcon aria-hidden="true" />
      </IconButton>
    </div>
  ),
}

export const IconButtonFocusState: Story = {
  render: () => (
    <IconButton aria-label="Focused notifications">
      <BellIcon aria-hidden="true" />
    </IconButton>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("button", { name: "Focused notifications" })
    ).toHaveFocus()
  },
}

export const IconButtonHoverState: Story = {
  render: () => (
    <IconButton aria-label="Hovered notifications">
      <BellIcon aria-hidden="true" />
    </IconButton>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.hover(
      within(canvasElement).getByRole("button", {
        name: "Hovered notifications",
      })
    )
  },
}

export const IconButtonActiveState: Story = {
  render: () => (
    <IconButton data-pressed="" aria-label="Active notifications">
      <BellIcon aria-hidden="true" />
    </IconButton>
  ),
}

export const IconButtonErrorState: Story = {
  render: () => (
    <IconButton aria-invalid="true" aria-label="Invalid notifications">
      <BellIcon aria-hidden="true" />
    </IconButton>
  ),
}

function SearchInputExample() {
  const [value, setValue] = useState("retained session")

  return (
    <SearchInput
      aria-label="Search sessions"
      value={value}
      onChange={(event) => setValue(event.currentTarget.value)}
      onClear={() => setValue("")}
    />
  )
}

export const InputStates: Story = {
  render: () => (
    <div className="grid max-w-md gap-3">
      <label htmlFor="player-handle" className="grid gap-1 text-sm font-medium">
        Player handle
        <Input id="player-handle" placeholder="poucet" />
      </label>
      <label htmlFor="dense-input" className="grid gap-1 text-sm font-medium">
        Dense input
        <Input id="dense-input" density="dense" defaultValue="session-42" />
      </label>
      <label htmlFor="invalid-input" className="grid gap-1 text-sm font-medium">
        Invalid input
        <Input
          id="invalid-input"
          aria-invalid="true"
          aria-describedby="input-error"
          defaultValue="invalid"
        />
        <span id="input-error" className="text-xs text-content-primary">
          Use a retained session identifier.
        </span>
      </label>
      <Input
        aria-label="Disabled input"
        disabled
        value="Unavailable"
        readOnly
      />
    </div>
  ),
}

export const InputFocusState: Story = {
  render: () => <Input aria-label="Focused input" defaultValue="session-42" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("textbox", { name: "Focused input" })
    ).toHaveFocus()
  },
}

export const InputErrorState: Story = {
  render: () => (
    <Input
      aria-label="Invalid input"
      aria-invalid="true"
      defaultValue="invalid"
    />
  ),
}

export const SearchInputStates: Story = {
  render: () => (
    <div className="grid max-w-md gap-3">
      <SearchInputExample />
      <SearchInput aria-label="Empty search" placeholder="Search experiments" />
      <SearchInput
        aria-label="Disabled search"
        disabled
        value="Unavailable"
        readOnly
      />
    </div>
  ),
}

export const SearchInputFocusState: Story = {
  render: () => <SearchInput aria-label="Focused session search" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("searchbox", { name: "Focused session search" })
    ).toHaveFocus()
  },
}

export const SearchInputErrorState: Story = {
  render: () => (
    <SearchInput aria-label="Invalid session search" aria-invalid="true" />
  ),
}

export const BadgeStates: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {(
        [
          "default",
          "secondary",
          "destructive",
          "outline",
          "ghost",
          "link",
        ] as const
      ).map((variant) => (
        <Badge key={variant} variant={variant}>
          {variant}
        </Badge>
      ))}
      <Badge render={<a href="#badge-contract" aria-label="Linked badge" />}>
        <SearchIcon aria-hidden="true" data-icon="inline-start" />
        Linked
      </Badge>
    </div>
  ),
}

export const BadgeLinkFocusState: Story = {
  render: () => (
    <Badge render={<a href="#badge-focus" aria-label="Focused badge link" />}>
      Focused badge link
    </Badge>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("link", { name: "Focused badge link" })
    ).toHaveFocus()
  },
}

export const BadgeLinkHoverState: Story = {
  render: () => (
    <Badge render={<a href="#badge-hover" aria-label="Hovered badge link" />}>
      Hovered badge link
    </Badge>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.hover(
      within(canvasElement).getByRole("link", {
        name: "Hovered badge link",
      })
    )
  },
}

export const StatusBadgeStates: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {(
        [
          "idle",
          "checking",
          "running",
          "succeeded",
          "stopped",
          "failed",
        ] as const
      ).map((status) => (
        <StatusBadge key={status} status={status}>
          {status}
        </StatusBadge>
      ))}
    </div>
  ),
}
