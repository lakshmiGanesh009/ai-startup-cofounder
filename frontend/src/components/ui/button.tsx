// Buttons, in three weights: primary for the one action a view is for,
// secondary for the rest, quiet for tools that should not draw the eye.

import Link from "next/link";

type Variant = "primary" | "secondary" | "quiet";
type Size = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-45";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-primary-ink shadow-[0_1px_1px_rgb(0_0_0/0.08)] hover:bg-primary-hover",
  secondary: "border border-rule-strong bg-surface text-ink hover:border-ink-3 hover:bg-sunken/60",
  quiet: "text-ink-2 hover:bg-sunken hover:text-ink",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-2.5 text-[13px]",
  md: "h-9 px-3.5 text-sm",
};

export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra = "") {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${extra}`;
}

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button type="button" {...props} className={buttonClass(variant, size, className)} />;
}

export function ButtonLink({
  variant = "secondary",
  size = "md",
  className = "",
  href,
  children,
}: {
  variant?: Variant;
  size?: Size;
  className?: string;
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

// A keyboard shortcut, shown inside a button.
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-current/25 px-1 font-sans text-[11px] leading-4 font-medium opacity-70">
      {children}
    </kbd>
  );
}
