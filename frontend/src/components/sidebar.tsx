"use client";

// The app's sidebar: the pages, the backend's status and the reasoning sliders.

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BackendStatus } from "@/components/backend-status";
import { ReasoningSliders } from "@/components/reasoning-sliders";

// The Streamlit UI keeps the Reports page until this app has its own.
const STREAMLIT_URL = process.env.NEXT_PUBLIC_STREAMLIT_URL ?? "http://localhost:8501";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex flex-col gap-6 border-b border-zinc-200 bg-surface p-5 lg:sticky lg:top-0 lg:h-dvh lg:w-72 lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0 dark:border-zinc-800">
      <div>
        <p className="text-xs font-semibold tracking-wide text-accent uppercase">AI Startup</p>
        <p className="text-lg font-semibold">Co-Founder Team</p>
      </div>
      <nav aria-label="Pages" className="flex flex-col gap-1 text-sm">
        <Link
          href="/"
          aria-current={pathname === "/" ? "page" : undefined}
          className={`rounded-md px-3 py-2 ${
            pathname === "/"
              ? "bg-accent-soft/60 font-medium text-navy dark:bg-accent/20 dark:text-accent-soft"
              : "hover:bg-zinc-100 dark:hover:bg-zinc-800"
          }`}
        >
          Evaluate
        </Link>
        <a
          href={`${STREAMLIT_URL}/reports_page`}
          className="rounded-md px-3 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          Reports <span className="text-xs text-zinc-500">(Streamlit, for now)</span>
        </a>
      </nav>
      <BackendStatus />
      <ReasoningSliders />
    </aside>
  );
}
