// Form fields: one look for every input, so forms read as a whole.

export const inputClass =
  "block w-full rounded-md border border-rule-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 " +
  "transition-[border-color,box-shadow] focus:border-focus focus:ring-3 focus:ring-focus/20 focus:outline-none disabled:opacity-60";

export function Label({ htmlFor, children, hint }: { htmlFor: string; children: React.ReactNode; hint?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between gap-3 text-[13px] font-medium text-ink">
      <span>{children}</span>
      {hint && <span className="text-xs font-normal text-ink-3">{hint}</span>}
    </label>
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        {...props}
        className={`${inputClass} appearance-none pr-9 ${props.className ?? ""}`}
      />
      <svg
        aria-hidden
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-3"
      >
        <path d="m4 6 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
