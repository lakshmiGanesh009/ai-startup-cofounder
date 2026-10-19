// A page's title and what the page is for.

export function PageHeader({
  title,
  description,
  aside,
}: {
  title: string;
  description: string;
  aside?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 border-b border-rule pb-6">
      <div className="max-w-2xl">
        <h1 className="font-serif text-[2rem] leading-tight font-medium tracking-[-0.01em]">{title}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{description}</p>
      </div>
      {aside}
    </header>
  );
}

// The size for a document's title. The Chief of Staff's objectives run from a
// line to a paragraph, so the longer ones are set smaller to stay a title.
export function titleSize(title: string): string {
  if (title.length <= 100) return "text-[1.75rem]";
  if (title.length <= 180) return "text-[1.5rem]";
  return "text-[1.3rem]";
}
