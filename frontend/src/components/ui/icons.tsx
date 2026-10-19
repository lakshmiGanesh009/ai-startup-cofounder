// The app's icons: 16-pixel line drawings on one stroke weight, so they sit
// with the text rather than decorate it. Each is hidden from screen readers;
// the control it sits in carries the words.

type IconProps = { className?: string };

function Icon({ className = "size-4", children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
    >
      {children}
    </svg>
  );
}

export function CompassIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M10.4 5.6 9.1 9.1 5.6 10.4 6.9 6.9z" />
    </Icon>
  );
}

export function DocumentIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9.5 1.75H4.25A1.25 1.25 0 0 0 3 3v10a1.25 1.25 0 0 0 1.25 1.25h7.5A1.25 1.25 0 0 0 13 13V5.25z" />
      <path d="M9.5 1.75v3.5H13M5.75 8.5h4.5M5.75 11h3" />
    </Icon>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m3.5 8.5 3 3 6-7" />
    </Icon>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m4 4 8 8m0-8-8 8" />
    </Icon>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </Icon>
  );
}

export function PencilIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m10.5 2.5 3 3L6 13H3v-3z" />
    </Icon>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 2.5v8m-3.5-3.5L8 10.5 11.5 7M3 13.5h10" />
    </Icon>
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M13.25 8a5.25 5.25 0 1 1-1.7-3.87M13.25 2.5v3.25H10" />
    </Icon>
  );
}

export function UndoIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.75 8a5.25 5.25 0 1 0 1.7-3.87M2.75 2.5v3.25H6" />
    </Icon>
  );
}

export function MoreIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" fill="currentColor" className={`shrink-0 ${className}`}>
      <circle cx="3.5" cy="8" r="1.25" />
      <circle cx="8" cy="8" r="1.25" />
      <circle cx="12.5" cy="8" r="1.25" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 2.25 14.25 13.5H1.75z" />
      <path d="M8 6.75v3" />
      <path d="M8 11.9v.1" strokeWidth={2} />
    </Icon>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 7.25v4" />
      <path d="M8 4.9v.1" strokeWidth={2} />
    </Icon>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" />
    </Icon>
  );
}
