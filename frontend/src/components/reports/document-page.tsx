"use client";

// The document studio as a page of its own: the whole window beside the
// sidebar (all of it on a phone, under no bar), with the way back to the
// report. The Reports page puts it in the address, so the browser's Back
// button returns to the report too.

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ArrowLeftIcon } from "@/components/ui/icons";

export function DocumentPage({
  kind,
  version,
  title,
  onBack,
  children,
}: {
  kind: string;
  version: number;
  title: string;
  onBack: () => void;
  children: React.ReactNode;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);

  // The button that opened it is gone, so the page takes the focus, unless
  // the studio has already put it in its prompt.
  useEffect(() => {
    if (!document.activeElement || document.activeElement === document.body) titleRef.current?.focus();
  }, []);

  return (
    <section
      aria-label="Document studio"
      className="fixed inset-0 z-40 flex flex-col bg-surface lg:left-[var(--sidebar-width,15rem)] lg:z-20"
    >
      <header className="flex shrink-0 items-center gap-4 border-b border-rule px-4 py-3 sm:px-5">
        <Button size="sm" onClick={onBack}>
          <ArrowLeftIcon />
          Back to the report
        </Button>
        <div className="min-w-0 flex-1">
          <p className="kicker">
            {kind} · <span className="tabular">Version {version}</span>
          </p>
          <h1 ref={titleRef} tabIndex={-1} className="truncate font-serif text-xl font-medium outline-none">
            {title}
          </h1>
        </div>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}
