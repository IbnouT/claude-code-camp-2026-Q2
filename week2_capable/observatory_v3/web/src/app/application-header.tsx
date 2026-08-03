import { TelescopeIcon } from "lucide-react"
import { type ReactNode } from "react"
import { Link } from "@tanstack/react-router"

import { SessionSelector } from "@/app/session-selector"
import { ThemeControl } from "@/app/theme-control"
import type {
  SessionCatalogItem,
  SessionCatalogState,
} from "@/data/session-catalog"

type ApplicationHeaderProps = {
  actions: ReactNode
  brandContext: {
    player?: string
    session?: string
  }
  navigation: ReactNode
  onSelect: (session: SessionCatalogItem) => void
  onSelectPlayer: (playerId: string) => void
  selected: SessionCatalogItem | null
  sessionCatalog: SessionCatalogState
}

function ApplicationHeader({
  actions,
  brandContext,
  navigation,
  onSelect,
  onSelectPlayer,
  selected,
  sessionCatalog,
}: ApplicationHeaderProps) {
  return (
    <header
      data-testid="application-header"
      className="relative z-30 flex min-h-(--header-height) items-center gap-4 border-b border-line bg-surface px-[22px] py-[13px] leading-[normal] max-[900px]:flex-wrap max-[700px]:items-stretch max-[700px]:px-3 max-[700px]:py-2.5"
    >
      <Link
        to="/live"
        search={{
          ...brandContext,
          view: "overview",
        }}
        aria-label="Boukensha Observatory"
        className="inline-flex flex-none items-center gap-[11px] text-[15px] font-semibold text-content-primary no-underline outline-none focus-visible:[box-shadow:var(--focus-ring)]"
      >
        <span
          data-testid="brand-mark"
          className="grid size-8 place-items-center rounded-[10px] border border-line-strong bg-[radial-gradient(120%_120%_at_30%_20%,#123639,#0a171c)] text-accent shadow-[inset_0_0_0_1px_rgb(104_225_220_/_18%)]"
        >
          <TelescopeIcon aria-hidden="true" className="size-[19px]" />
        </span>
        <span className="grid gap-px max-[1040px]:hidden">
          <strong className="text-[15px] font-semibold">Boukensha</strong>
          <small className="text-[8.5px] font-medium tracking-[0.16em] text-content-quiet uppercase in-data-[theme=light]:text-content-muted">
            Observatory
          </small>
        </span>
      </Link>

      <nav
        aria-label="Observatory spaces"
        className="ml-1.5 inline-flex items-center gap-[3px] max-[700px]:order-3 max-[700px]:ml-0 max-[700px]:w-full max-[700px]:overflow-x-auto [&>a]:inline-flex [&>a]:items-center [&>a]:gap-[7px] [&>a]:rounded-[10px] [&>a]:border-0 [&>a]:px-3.5 [&>a]:py-2 [&>a]:text-[13.5px] [&>a]:leading-[normal] [&>a]:font-medium [&>a]:outline-none [&>a]:focus-visible:[box-shadow:var(--focus-ring)] max-[1040px]:[&>a]:px-2.5 max-[1040px]:[&>a>span]:hidden"
      >
        {navigation}
      </nav>

      <div className="ml-auto flex min-w-0 items-center justify-end gap-[7px] max-[700px]:ml-0 max-[700px]:w-full max-[700px]:flex-wrap max-[700px]:justify-start">
        <SessionSelector
          catalogResult={sessionCatalog.result}
          isLoadingAllSessions={sessionCatalog.isLoadingAllSessions}
          loadAllSessions={sessionCatalog.loadAllSessions}
          selected={selected}
          onRefresh={sessionCatalog.refresh}
          onSelect={onSelect}
          onSelectPlayer={onSelectPlayer}
          playerComplete={sessionCatalog.playerComplete}
        />
        {actions}
        <ThemeControl />
      </div>
    </header>
  )
}

export { ApplicationHeader, type ApplicationHeaderProps }
