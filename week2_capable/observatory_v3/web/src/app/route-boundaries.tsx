import type { ErrorComponentProps } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

function BoundaryCard({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <Card className="max-w-xl" aria-live="polite">
      <CardHeader>
        <CardTitle>
          <h1>{title}</h1>
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {action === undefined ? null : <CardContent>{action}</CardContent>}
    </Card>
  )
}

function RoutePendingBoundary() {
  return (
    <BoundaryCard
      title="Loading route"
      description="Preparing the requested Observatory section."
    />
  )
}

function RouteErrorBoundary({ error, reset }: ErrorComponentProps) {
  return (
    <BoundaryCard
      title="Route unavailable"
      description={
        error instanceof Error
          ? error.message
          : "The requested route could not be prepared."
      }
      action={<Button onClick={reset}>Try route again</Button>}
    />
  )
}

function RouteNotFoundBoundary() {
  return (
    <BoundaryCard
      title="Route not found"
      description="This Observatory location does not exist."
    />
  )
}

export { RouteErrorBoundary, RouteNotFoundBoundary, RoutePendingBoundary }
