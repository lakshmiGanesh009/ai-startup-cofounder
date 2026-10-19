"use client";

// A small menu behind a button, for actions that should be there without
// competing with the main ones. It closes on a choice, a click elsewhere or Esc.

import { useEffect, useId, useRef, useState } from "react";

import { buttonClass } from "@/components/ui/button";
import { MoreIcon } from "@/components/ui/icons";

export type MenuItem = { label: string; description?: string; icon?: React.ReactNode; onSelect: () => void };

export function Menu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((current) => !current)}
        className={buttonClass("secondary", "md", "px-2.5")}
      >
        <MoreIcon />
        <span className="sr-only">{label}</span>
      </button>
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={label}
          className="absolute right-0 z-20 mt-1.5 w-72 overflow-hidden rounded-lg border border-rule bg-surface p-1 shadow-[0_8px_24px_rgb(0_0_0/0.12)]"
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className="flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left hover:bg-sunken focus-visible:bg-sunken"
            >
              {item.icon && <span className="mt-0.5 text-ink-2">{item.icon}</span>}
              <span>
                <span className="block text-sm font-medium text-ink">{item.label}</span>
                {item.description && <span className="mt-0.5 block text-xs leading-snug text-ink-3">{item.description}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
