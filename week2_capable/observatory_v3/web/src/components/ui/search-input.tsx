import { SearchIcon, XIcon } from "lucide-react"
import { forwardRef, useId, type ComponentProps } from "react"

import { IconButton } from "@/components/ui/icon-button"
import { Input, type InputProps } from "@/components/ui/input"
import { cn } from "@/lib/utils"

type SearchInputProps = Omit<InputProps, "type"> & {
  clearLabel?: string
  onClear?: () => void
}

const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  (
    {
      className,
      clearLabel = "Clear search",
      id: providedId,
      onClear,
      value,
      ...props
    },
    ref
  ) => {
    const generatedId = useId()
    const id = providedId ?? generatedId
    const hasValue =
      typeof value === "string" || typeof value === "number"
        ? String(value).length > 0
        : false

    return (
      <div
        data-slot="search-input"
        className="relative flex w-full items-center"
      >
        <SearchIcon
          aria-hidden="true"
          className="pointer-events-none absolute left-2.5 size-4 text-content-muted"
        />
        <Input
          ref={ref}
          id={id}
          type="search"
          value={value}
          className={cn(
            "pr-8 pl-8 [&::-webkit-search-cancel-button]:hidden",
            className
          )}
          {...props}
        />
        {onClear !== undefined && hasValue ? (
          <IconButton
            type="button"
            aria-label={clearLabel}
            variant="ghost"
            size="icon-xs"
            className="absolute right-1"
            onClick={onClear}
          >
            <XIcon aria-hidden="true" />
          </IconButton>
        ) : null}
      </div>
    )
  }
)

SearchInput.displayName = "SearchInput"

type SearchInputElementProps = ComponentProps<typeof SearchInput>

export { SearchInput, type SearchInputElementProps, type SearchInputProps }
