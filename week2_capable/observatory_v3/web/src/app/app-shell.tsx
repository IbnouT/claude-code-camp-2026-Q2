import { Outlet, useRouterState } from "@tanstack/react-router"
import { useEffect, useRef, type ReactNode } from "react"

type AppShellProps = {
  navigation: ReactNode
}

function AppShell({ navigation }: AppShellProps) {
  const contentRef = useRef<HTMLElement>(null)
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const isReviewRoute = pathname === "/review"

  useEffect(() => {
    contentRef.current?.focus()
  }, [pathname])

  return (
    <div
      data-testid="application-shell"
      className="min-h-svh bg-canvas text-content-primary"
    >
      <div
        className={
          isReviewRoute
            ? "flex min-h-svh w-full flex-col"
            : "mx-auto grid min-h-svh w-full max-w-7xl md:grid-cols-[13rem_1fr]"
        }
      >
        <aside
          className={
            isReviewRoute
              ? "border-b border-line bg-surface p-4"
              : "border-b border-line bg-surface p-4 md:border-r md:border-b-0 md:p-5"
          }
        >
          <div className="text-xs font-semibold tracking-[0.18em] text-accent uppercase">
            Boukensha Observatory
          </div>
          <nav
            aria-label="Observatory sections"
            className={
              isReviewRoute
                ? "mt-4 flex flex-wrap gap-2"
                : "mt-4 flex flex-wrap gap-2 md:flex-col"
            }
          >
            {navigation}
          </nav>
        </aside>
        <main
          ref={contentRef}
          tabIndex={-1}
          data-testid="route-content"
          className={
            isReviewRoute
              ? "min-w-0 flex-1 outline-none"
              : "min-w-0 p-5 outline-none sm:p-8"
          }
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export { AppShell, type AppShellProps }
