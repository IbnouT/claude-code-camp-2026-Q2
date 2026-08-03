import {
  BellIcon,
  ChevronDownIcon,
  GitCompareArrowsIcon,
  MoonIcon,
  MoreHorizontalIcon,
} from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { IconButton } from "@/components/ui/icon-button"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import { SearchInput } from "@/components/ui/search-input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { StatusBadge } from "@/components/ui/status-badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

const variants = [
  "default",
  "secondary",
  "outline",
  "ghost",
  "destructive",
  "link",
] as const

const statuses = [
  "idle",
  "checking",
  "running",
  "succeeded",
  "stopped",
  "failed",
] as const

export function PrimitiveReview() {
  const [search, setSearch] = useState("session")

  return (
    <section
      aria-labelledby="primitive-review-title"
      className="border-t border-line py-8"
      data-testid="primitive-review"
    >
      <div className="mb-6">
        <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">
          Canonical component layer
        </p>
        <h2 id="primitive-review-title" className="mt-2 text-2xl font-semibold">
          Observatory UI primitives
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-content-muted">
          Repository-owned presentation with Base UI behavior, semantic tokens,
          strict interfaces, and isolated interaction states.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Retained primitive parity</CardTitle>
            <CardDescription>
              Frozen-source specimens for browser style and screenshot proof.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <IconButton
                data-testid="retained-icon-button-specimen"
                aria-label="Use dark theme"
              >
                <MoonIcon aria-hidden="true" size={16} />
              </IconButton>
              <StatusBadge
                data-testid="retained-status-badge-specimen"
                status="succeeded"
              >
                standing
              </StatusBadge>
              <Input
                data-testid="retained-input-specimen"
                aria-label="Ask about this session"
                placeholder="Ask why, find a trace, or search exact evidence"
                className="w-[586.766px] max-w-full"
              />
              <Collapsible className="w-[340px] overflow-hidden rounded-xl border border-line-strong bg-surface">
                <CollapsibleTrigger
                  data-testid="retained-disclosure-specimen"
                  variant="retained"
                >
                  <span>Agent · Planning · 24h ago</span>
                  <ChevronDownIcon aria-hidden="true" className="size-3.5" />
                </CollapsibleTrigger>
              </Collapsible>
            </div>
            <Tabs defaultValue="compare">
              <TabsList variant="retained" aria-label="Experiment lenses">
                <TabsTrigger
                  data-testid="retained-tab-specimen"
                  value="compare"
                >
                  <GitCompareArrowsIcon
                    aria-hidden="true"
                    className="size-3.5"
                  />
                  Compare
                </TabsTrigger>
                <TabsTrigger value="paths">Paths</TabsTrigger>
              </TabsList>
            </Tabs>
            <Dialog>
              <DialogTrigger render={<Button variant="outline" />}>
                Open retained dialog
              </DialogTrigger>
              <DialogContent
                retained
                showCloseButton={false}
                data-testid="retained-dialog-specimen"
                className="h-[172px]"
              >
                <div className="p-4">Ask about this session</div>
              </DialogContent>
            </Dialog>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Controls</CardTitle>
            <CardDescription>
              Variants, density, disabled, and error states.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex flex-wrap gap-2">
              {variants.map((variant) => (
                <Button key={variant} variant={variant}>
                  {variant}
                </Button>
              ))}
              <Button data-testid="retained-action-specimen">
                Start session as poucet →
              </Button>
              <IconButton aria-label="Notifications" variant="outline">
                <BellIcon aria-hidden="true" />
              </IconButton>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                aria-label="Session identifier"
                defaultValue="session-42"
              />
              <Input
                aria-label="Invalid identifier"
                aria-invalid="true"
                defaultValue="invalid"
              />
              <SearchInput
                aria-label="Search sessions"
                value={search}
                onChange={(event) => setSearch(event.currentTarget.value)}
                onClear={() => setSearch("")}
              />
              <Select defaultValue="running">
                <SelectTrigger aria-label="Lifecycle state">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="succeeded">Succeeded</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Status and navigation</CardTitle>
            <CardDescription>
              Lifecycle semantics and keyboard-owned selection.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex flex-wrap gap-2">
              {statuses.map((status) => (
                <StatusBadge key={status} status={status}>
                  {status}
                </StatusBadge>
              ))}
              <Badge variant="outline">bounded</Badge>
            </div>
            <Tabs defaultValue="live">
              <TabsList aria-label="Resource partition">
                <TabsTrigger value="live">Live</TabsTrigger>
                <TabsTrigger value="sessions">Sessions</TabsTrigger>
                <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
              </TabsList>
              <TabsContent value="live">Live partition selected.</TabsContent>
              <TabsContent value="sessions">
                Sessions partition selected.
              </TabsContent>
              <TabsContent value="knowledge">
                Knowledge partition selected.
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Disclosure</CardTitle>
            <CardDescription>
              Focus restoration, escape, and expanded state come from Base UI.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-start gap-3">
            <Dialog>
              <DialogTrigger render={<Button />}>Open dialog</DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Primitive dialog</DialogTitle>
                  <DialogDescription>
                    Escape closes the dialog and restores trigger focus.
                  </DialogDescription>
                </DialogHeader>
              </DialogContent>
            </Dialog>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger render={<Button variant="outline" />}>
                  Focus tooltip
                </TooltipTrigger>
                <TooltipContent>Accessible supporting context</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Popover>
              <PopoverTrigger render={<Button variant="outline" />}>
                Open popover
              </PopoverTrigger>
              <PopoverContent>
                <PopoverTitle>Composite cursor</PopoverTitle>
                <PopoverDescription>
                  The cursor covers every governed partition.
                </PopoverDescription>
              </PopoverContent>
            </Popover>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <IconButton variant="outline" aria-label="Primitive actions">
                    <MoreHorizontalIcon aria-hidden="true" />
                  </IconButton>
                }
              />
              <DropdownMenuContent>
                <DropdownMenuItem>Inspect resource</DropdownMenuItem>
                <DropdownMenuItem disabled>Unavailable action</DropdownMenuItem>
                <DropdownMenuItem variant="destructive">
                  Remove local view
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Collapsible className="w-full rounded-lg border border-line p-2">
              <CollapsibleTrigger
                render={
                  <Button variant="ghost" className="w-full justify-between" />
                }
              >
                Resource detail
                <ChevronDownIcon aria-hidden="true" />
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pt-2 text-sm text-content-muted">
                Bounded resource detail renders on demand.
              </CollapsibleContent>
            </Collapsible>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Scroll area</CardTitle>
            <CardDescription>
              Native scrolling with repository-owned track and thumb styling.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-40 rounded-lg border border-line">
              <div className="grid gap-2 p-3">
                {Array.from({ length: 12 }, (_, index) => (
                  <div
                    key={index}
                    className="rounded-md bg-surface-soft px-3 py-2 text-sm"
                  >
                    Resource {String(index + 1).padStart(2, "0")}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
