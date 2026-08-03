import type { Meta, StoryObj } from "@storybook/react-vite"
import { expect, userEvent, within } from "storybook/test"

import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const meta = {
  title: "Primitives/Navigation and scroll",
  component: Tabs,
  tags: ["autodocs"],
} satisfies Meta<typeof Tabs>

export default meta

type Story = StoryObj<typeof meta>

export const TabsStates: Story = {
  render: () => (
    <div className="grid max-w-xl gap-6">
      <Tabs defaultValue="live">
        <TabsList aria-label="Resource partition">
          <TabsTrigger value="live">Live</TabsTrigger>
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
          <TabsTrigger value="disabled" disabled>
            Disabled
          </TabsTrigger>
        </TabsList>
        <TabsContent value="live">Live partition content.</TabsContent>
        <TabsContent value="sessions">Session partition content.</TabsContent>
      </Tabs>
      <Tabs defaultValue="events">
        <TabsList variant="line" aria-label="Detail view">
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="trace">Trace</TabsTrigger>
        </TabsList>
        <TabsContent value="events">Event detail.</TabsContent>
        <TabsContent value="trace">Trace detail.</TabsContent>
      </Tabs>
    </div>
  ),
}

export const TabsFocusState: Story = {
  render: () => (
    <Tabs defaultValue="compare">
      <TabsList variant="retained" aria-label="Focused experiment lens">
        <TabsTrigger value="compare">Compare</TabsTrigger>
        <TabsTrigger value="paths">Paths</TabsTrigger>
      </TabsList>
    </Tabs>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(canvas.getByRole("tab", { name: "Compare" })).toHaveFocus()
  },
}

export const ScrollAreaStates: Story = {
  render: () => (
    <div className="grid gap-4">
      <ScrollArea className="h-40 w-72 rounded-lg border border-line bg-surface">
        <div className="grid gap-2 p-3">
          {Array.from({ length: 16 }, (_, index) => (
            <div
              key={index}
              className="rounded-md bg-surface-soft px-3 py-2 text-sm"
            >
              Resource {String(index + 1).padStart(2, "0")}
            </div>
          ))}
        </div>
      </ScrollArea>
      <ScrollArea className="w-72 rounded-lg border border-line bg-surface">
        <div className="flex w-max gap-2 p-3">
          {Array.from({ length: 12 }, (_, index) => (
            <span
              key={index}
              className="rounded-md bg-surface-soft px-4 py-2 text-sm"
            >
              Partition {index + 1}
            </span>
          ))}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  ),
}

export const ScrollAreaFocusState: Story = {
  render: () => (
    <ScrollArea
      tabIndex={0}
      aria-label="Focused resource list"
      className="h-40 w-72 rounded-lg border border-line bg-surface"
    >
      <div className="grid gap-2 p-3">
        <div className="rounded-md bg-surface-soft px-3 py-2 text-sm">
          Resource 01
        </div>
      </div>
    </ScrollArea>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.tab()
    await expect(
      canvas.getByRole("region", { name: "Focused resource list" })
    ).toHaveFocus()
  },
}
