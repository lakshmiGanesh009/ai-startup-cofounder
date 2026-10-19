"use client";

// A modal pop-up on the browser's own <dialog>, which traps focus and closes
// on Esc. It also closes when its page is hidden on navigation, or the next
// page would stay blocked behind it.

import { useEffect, useId, useLayoutEffect, useRef } from "react";

export function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useId();

  useEffect(() => {
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
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(72rem,calc(100vw-2rem))] rounded-xl bg-surface p-0 text-foreground shadow-2xl backdrop:bg-black/50"
    >
      {open && (
        <>
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-zinc-200 bg-surface px-5 py-3 dark:border-zinc-800">
            <h2 id={heading} className="text-lg font-semibold">
              {title}
            </h2>
            <button
              type="button"
              aria-label="Close"
              onClick={onClose}
              className="rounded-md px-2 py-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            >
              ✕
            </button>
          </header>
          <div className="p-5">{children}</div>
        </>
      )}
    </dialog>
  );
}
