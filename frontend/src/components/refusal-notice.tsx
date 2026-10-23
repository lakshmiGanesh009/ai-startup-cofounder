// Azure OpenAI refused what a request asked, by its safety policy (llm.py's
// refused): a warning in red, apart from a failure, since it is the request
// to change, not something to try again as it is.

import { useEffect, useId, useRef } from "react";

import { AlertIcon } from "@/components/ui/icons";

export function RefusalNotice({ detail, className = "" }: { detail: string; className?: string }) {
  const title = useId();
  const notice = useRef<HTMLDivElement>(null);
  // Brought into view: the request it answers may have been sent from far above it.
  useEffect(() => {
    notice.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [detail]);
  return (
    <div
      ref={notice}
      role="alert"
      aria-labelledby={title}
      className={`rounded-lg border border-bad/40 border-l-4 border-l-bad bg-bad-soft px-4 py-3.5 ${className}`}
    >
      <p id={title} className="flex items-center gap-2 font-serif text-lg leading-snug text-bad">
        <AlertIcon className="size-5 shrink-0" />
        The team won’t work on this request
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink">{detail}</p>
      <p className="kicker mt-2.5 text-bad">Refused by Azure OpenAI’s safety policy</p>
    </div>
  );
}
