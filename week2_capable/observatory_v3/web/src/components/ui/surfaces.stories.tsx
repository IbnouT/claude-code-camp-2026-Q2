import type { Meta, StoryObj } from "@storybook/react-vite"

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"

const meta = {
  title: "Primitives/Card",
  component: Card,
  tags: ["autodocs"],
} satisfies Meta<typeof Card>

export default meta

type Story = StoryObj<typeof meta>

export const CardStates: Story = {
  render: () => (
    <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Session materialization</CardTitle>
          <CardDescription>
            Stable partitions fetched through typed resources.
          </CardDescription>
          <CardAction>
            <Button size="xs" variant="outline">
              Inspect
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <p>42 bounded resources are ready.</p>
        </CardContent>
        <CardFooter>Updated from the composite cursor.</CardFooter>
      </Card>
      <Card size="sm">
        <CardHeader>
          <CardTitle>Dense card</CardTitle>
          <CardDescription>Compact workshop state.</CardDescription>
        </CardHeader>
        <CardContent>One responsibility per surface.</CardContent>
      </Card>
    </div>
  ),
}
