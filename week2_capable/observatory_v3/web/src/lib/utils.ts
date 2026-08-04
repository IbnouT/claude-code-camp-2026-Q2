import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

/**
 * The launcher type scale extends Tailwind's font-size utilities. The merge
 * helper must know these are sizes, not colors, or it drops a real color
 * utility as a false conflict.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "launcher-title",
            "launcher-heading",
            "launcher-name",
            "launcher-base",
            "launcher-chip",
            "launcher-note",
            "launcher-detail",
            "launcher-caption",
            "launcher-fine",
            "launcher-sigil",
            "launcher-sigil-lg",
          ],
        },
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
