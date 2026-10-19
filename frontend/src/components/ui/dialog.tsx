"use client";

// A modal pop-up on the browser's own <dialog>, which traps focus and closes
// on Esc. It also closes when its page is hidden on navigation, or the next
// page would stay blocked behind it.

import { useId, useLayoutEffect, useRef } from "react";

import { CloseIcon } from "@/components/ui/icons";

const SIZES = {
  small: "w-[min(30rem,calc(100vw-2rem))]",
  large: "h-[calc(100dvh-2rem)] w-[min(96rem,calc(100vw-2rem))]",
};

export function Dialog({
  open,
  title,
  description,
  actions,
  size = "large",
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  size?: keyof typeof SIZES;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useId();

  // A layout effect, so the dialog is open before its contents' effects run:
  // showModal() moves focus to its first control, and a child that focuses
  // something else (the PDF panel's prompt) must come after.
  useLayoutEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useLayoutEffect(() => {
    const dialog = ref.current;
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={heading}
      onClose={onClose}
      className={`m-auto max-h-[calc(100dvh-2rem)] overflow-hidden rounded-xl border border-rule bg-surface p-0 text-ink shadow-[0_24px_64px_rgb(0_0_0/0.25)] ${SIZES[size]}`}
    >
      {open && (
        <div className="flex h-full max-h-[calc(100dvh-2rem)] flex-col">
          <header className="flex shrink-0 items-center gap-4 border-b border-rule px-5 py-3.5">
            <div className="min-w-0 flex-1">
              <h2 id={heading} className="truncate font-serif text-xl font-medium">
                {title}
              </h2>
              {description && <p className="truncate text-xs text-ink-3">{description}</p>}
            </div>
            {actions}
            <button
              type="button"
              aria-label="Close"
              onClick={onClose}
              className="rounded-md p-1.5 text-ink-3 hover:bg-sunken hover:text-ink"
            >
              <CloseIcon />
            </button>
          </header>
          <div className={size === "large" ? "min-h-0 flex-1" : "p-5"}>{children}</div>
        </div>
      )}
    </dialog>
  );
}
