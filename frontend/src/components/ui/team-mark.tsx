// The app's mark: the Chief of Staff at the centre and the four specialists
// around it, the shape of the team the app runs.

export function TeamMark({ className = "size-6" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className={className}>
      <g stroke="currentColor" strokeWidth={1.25} opacity={0.45}>
        <path d="M12 8.5V5M15.5 12H19M12 15.5V19M8.5 12H5" />
      </g>
      <g fill="currentColor">
        <circle cx="12" cy="12" r="3.25" />
        <circle cx="12" cy="3.5" r="2" />
        <circle cx="20.5" cy="12" r="2" />
        <circle cx="12" cy="20.5" r="2" />
        <circle cx="3.5" cy="12" r="2" />
      </g>
    </svg>
  );
}
