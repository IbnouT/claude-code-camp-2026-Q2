import { Search, Sparkles, X } from "lucide-react";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function CommandPalette({ open, onClose }: Props) {
  if (!open) {
    return null;
  }

  return (
    <div className="palette-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Ask or search evidence"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <label className="palette-input">
          <Search size={18} aria-hidden="true" />
          <input
            autoFocus
            type="search"
            placeholder="Ask why it stopped, or search kind:position confidence:<0.7"
          />
          <kbd>esc</kbd>
        </label>
        <div className="palette-content">
          <p className="eyebrow">Suggested investigations</p>
          <button type="button">
            <Sparkles size={15} aria-hidden="true" />
            Why did the agent believe the journey was complete?
          </button>
          <button type="button">
            <Search size={15} aria-hidden="true" />
            Show every low-confidence position in this run
          </button>
        </div>
        <button className="palette-close" type="button" onClick={onClose} aria-label="Close">
          <X size={17} aria-hidden="true" />
        </button>
      </section>
    </div>
  );
}
