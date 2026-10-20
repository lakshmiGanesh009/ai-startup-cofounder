"use client";

// Accessible tabs: arrow keys move between them, and every panel stays in the
// page (hidden when not selected), so switching keeps their state. Laid out
// across the top, or down the side as a list of chapters.

import { useId, useRef, useState } from "react";

export type Tab = { label: string; content: React.ReactNode; marker?: string };

export function Tabs({
  tabs,
  label,
  orientation = "horizontal",
  initial = 0,
  onSelect,
}: {
  tabs: Tab[];
  label: string;
  orientation?: "horizontal" | "vertical";
  initial?: number;
  // Told which tab is now open, for a panel that should work only while shown.
  onSelect?: (index: number) => void;
}) {
  const [active, setActive] = useState(initial);
  const id = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const vertical = orientation === "vertical";

  function select(index: number, focus = true) {
    const next = (index + tabs.length) % tabs.length;
    setActive(next);
    onSelect?.(next);
    if (focus) buttons.current[next]?.focus();
  }

  const list = (
    <div
      role="tablist"
      aria-label={label}
      aria-orientation={orientation}
      className={
        vertical
          ? "-mx-1 flex gap-1 overflow-x-auto pb-1 lg:sticky lg:top-8 lg:mx-0 lg:flex-col lg:gap-0 lg:self-start lg:overflow-visible"
          : "flex gap-6 overflow-x-auto border-b border-rule"
      }
    >
      {tabs.map((tab, index) => {
        const selected = index === active;
        return (
          <button
            key={tab.label}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${index}`}
            aria-selected={selected}
            aria-controls={`${id}-panel-${index}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => select(index, false)}
            onKeyDown={(event) => {
              const forward = vertical ? "ArrowDown" : "ArrowRight";
              const back = vertical ? "ArrowUp" : "ArrowLeft";
              if (event.key === forward) select(index + 1);
              if (event.key === back) select(index - 1);
            }}
            className={
              vertical
                ? `flex shrink-0 items-baseline gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors lg:rounded-none lg:border-l-2 lg:px-3 lg:py-2 ${
                    selected
                      ? "bg-sunken font-medium text-ink lg:border-primary lg:bg-transparent"
                      : "text-ink-3 hover:text-ink lg:border-transparent"
                  }`
                : `-mb-px shrink-0 border-b-2 py-2.5 text-sm font-medium transition-colors ${
                    selected ? "border-ink text-ink" : "border-transparent text-ink-3 hover:text-ink"
                  }`
            }
          >
            {tab.marker && (
              <span aria-hidden className="w-4 text-xs text-ink-3 tabular">
                {tab.marker}
              </span>
            )}
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );

  const panels = tabs.map((tab, index) => (
    <div
      key={tab.label}
      role="tabpanel"
      id={`${id}-panel-${index}`}
      aria-labelledby={`${id}-tab-${index}`}
      hidden={index !== active}
      className={vertical ? "min-w-0" : "pt-6"}
    >
      {tab.content}
      {vertical && tabs.length > 1 && index < tabs.length - 1 && (
        <div className="mt-14 border-t border-rule pt-5">
          <button
            type="button"
            onClick={() => {
              select(index + 1, false);
              window.scrollTo?.({ top: 0, behavior: "smooth" });
            }}
            className="group text-left"
          >
            <span className="kicker">Next</span>
            <span className="mt-0.5 block font-serif text-lg text-ink group-hover:underline group-hover:underline-offset-4">
              {tabs[index + 1].marker && `${tabs[index + 1].marker} `}
              {tabs[index + 1].label} →
            </span>
          </button>
        </div>
      )}
    </div>
  ));

  if (!vertical) {
    return (
      <div>
        {list}
        {panels}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-12">
      {list}
      <div>{panels}</div>
    </div>
  );
}
