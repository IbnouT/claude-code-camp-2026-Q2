import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

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
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { SearchInput } from "@/components/ui/search-input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

afterEach(cleanup)

describe("canonical UI primitives", () => {
  it("does not activate a disabled button", async () => {
    const user = userEvent.setup()
    const onClick = vi.fn<() => void>()
    render(
      <Button disabled onClick={onClick}>
        Disabled action
      </Button>
    )

    await user.click(screen.getByRole("button", { name: "Disabled action" }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it("clears a controlled search through its accessible icon action", async () => {
    const user = userEvent.setup()

    function SearchExample() {
      const [value, setValue] = useState("session")

      return (
        <SearchInput
          aria-label="Search sessions"
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
          onClear={() => setValue("")}
        />
      )
    }

    render(<SearchExample />)
    await user.click(screen.getByRole("button", { name: "Clear search" }))

    expect(
      screen.getByRole("searchbox", { name: "Search sessions" })
    ).toHaveValue("")
    expect(
      screen.queryByRole("button", { name: "Clear search" })
    ).not.toBeInTheDocument()
  })

  it("moves tab selection with the keyboard without activating disabled tabs", async () => {
    const user = userEvent.setup()
    render(
      <Tabs defaultValue="live">
        <TabsList aria-label="Resource partition">
          <TabsTrigger value="live">Live</TabsTrigger>
          <TabsTrigger value="disabled" disabled>
            Disabled
          </TabsTrigger>
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
        </TabsList>
        <TabsContent value="live">Live content</TabsContent>
        <TabsContent value="sessions">Session content</TabsContent>
      </Tabs>
    )

    await user.click(screen.getByRole("tab", { name: "Live" }))
    await user.keyboard("{ArrowRight}")

    const disabled = screen.getByRole("tab", { name: "Disabled" })
    expect(disabled).toHaveFocus()
    expect(disabled).toHaveAttribute("aria-selected", "false")

    await user.keyboard("{ArrowRight}")

    const sessions = screen.getByRole("tab", { name: "Sessions" })
    expect(sessions).toHaveFocus()

    await user.keyboard("{Enter}")

    expect(sessions).toHaveAttribute("aria-selected", "true")
    expect(
      screen.getByRole("tabpanel", { name: "Sessions" })
    ).toBeInTheDocument()
  })

  it("restores trigger focus when escape closes a dialog", async () => {
    const user = userEvent.setup()
    render(
      <Dialog>
        <DialogTrigger render={<Button />}>Open details</DialogTrigger>
        <DialogContent>
          <DialogTitle>Session details</DialogTitle>
          <DialogDescription>Bounded session resources.</DialogDescription>
        </DialogContent>
      </Dialog>
    )

    const trigger = screen.getByRole("button", { name: "Open details" })
    await user.click(trigger)
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    await user.keyboard("{Escape}")

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("reports the expanded state of a collapsible", async () => {
    const user = userEvent.setup()
    render(
      <Collapsible>
        <CollapsibleTrigger>Details</CollapsibleTrigger>
        <CollapsibleContent>Resource detail</CollapsibleContent>
      </Collapsible>
    )

    const trigger = screen.getByRole("button", { name: "Details" })
    expect(trigger).toHaveAttribute("aria-expanded", "false")

    await user.click(trigger)

    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("Resource detail")).toBeVisible()
  })
})
