import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

type RoutePlaceholderProps = {
  title: string
  routeState: string
}

function RoutePlaceholder({ title, routeState }: RoutePlaceholderProps) {
  return (
    <section aria-labelledby="route-title" className="max-w-3xl">
      <Badge variant="outline">Typed route boundary</Badge>
      <h1
        id="route-title"
        className="mt-4 text-3xl font-semibold tracking-tight"
      >
        {title}
      </h1>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>{title} route ready</CardTitle>
          <CardDescription>
            Feature content arrives in its owning landing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p
            data-testid="validated-route-state"
            className="font-mono text-xs text-content-muted"
          >
            {routeState}
          </p>
        </CardContent>
      </Card>
    </section>
  )
}

export { RoutePlaceholder, type RoutePlaceholderProps }
