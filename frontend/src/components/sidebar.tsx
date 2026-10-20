"use client";

// The app's rail: the mark, the pages, the reasoning sliders and whether the
// API answers. On a phone it folds into a bar with a menu.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { BackendStatus } from "@/components/backend-status";
import { ReasoningSliders } from "@/components/reasoning-sliders";
import { ResearchSwitch } from "@/components/research-switch";
import { CloseIcon, CompassIcon, DocumentIcon, FlowIcon, MenuIcon } from "@/components/ui/icons";
import { TeamMark } from "@/components/ui/team-mark";

const PAGES = [
  { href: "/", label: "Evaluate", Icon: CompassIcon },
  { href: "/reports", label: "Reports", Icon: DocumentIcon },
  { href: "/how-it-works", label: "How it works", Icon: FlowIcon },
];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 rounded-md">
      <TeamMark className="size-[22px] text-primary" />
      <span className="leading-none">
        <span className="block font-serif text-[1.2rem] font-semibold tracking-[-0.01em]">Co-Founder</span>
        <span className="mt-0.5 block text-[11px] text-ink-3">An AI founding team</span>
      </span>
    </Link>
  );
}

function Pages({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Pages" className="flex flex-col gap-0.5">
      {PAGES.map(({ href, label, Icon }) => {
        const current = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={current ? "page" : undefined}
            className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
              current
                ? "bg-surface font-medium text-ink shadow-[0_0_0_1px_var(--rule)]"
                : "text-ink-2 hover:bg-sunken hover:text-ink"
            }`}
          >
            <Icon className={`size-4 ${current ? "text-primary" : "text-ink-3"}`} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-rule bg-paper/95 px-4 py-3 backdrop-blur lg:hidden">
        <Brand />
        <button
          type="button"
          aria-expanded={open}
          aria-controls="app-menu"
          onClick={() => setOpen((current) => !current)}
          className="rounded-md p-2 text-ink-2 hover:bg-sunken"
        >
          {open ? <CloseIcon /> : <MenuIcon />}
          <span className="sr-only">{open ? "Close the menu" : "Open the menu"}</span>
        </button>
      </div>
      <aside
        id="app-menu"
        className={`${open ? "flex" : "hidden"} flex-col gap-8 border-b border-rule bg-paper px-4 py-5 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:w-60 lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0 lg:py-6`}
      >
        <div className="hidden px-1 lg:block">
          <Brand />
        </div>
        <Pages onNavigate={() => setOpen(false)} />
        <div className="px-1">
          <ReasoningSliders />
        </div>
        <div className="px-1">
          <ResearchSwitch />
        </div>
        <div className="mt-auto border-t border-rule px-1 pt-4">
          <BackendStatus />
        </div>
      </aside>
    </>
  );
}
