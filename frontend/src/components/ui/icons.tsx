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

// A file attached to the brief.
export function PaperclipIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m13.25 7.6-5.1 5.1a3.25 3.25 0 0 1-4.6-4.6l5.3-5.3a2.1 2.1 0 0 1 3 3l-5.25 5.25a1 1 0 0 1-1.4-1.4L10 4.85" />
    </Icon>
  );
}

// A question put to the documents.
export function QuestionIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.75 12.9V4.25a1.5 1.5 0 0 1 1.5-1.5h7.5a1.5 1.5 0 0 1 1.5 1.5v5.5a1.5 1.5 0 0 1-1.5 1.5H5.4z" />
      <path d="M6.6 5.9a1.45 1.45 0 1 1 1.9 1.4c-.3.1-.5.4-.5.7v.2M8 9.6v.05" />
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

export function ArrowLeftIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M13 8H3M7 4 3 8l4 4" />
    </Icon>
  );
}

// A thumb up, and turned over, down: the founder's verdict on a strategy.
export function ThumbUpIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 7.25h2.5v6.25h-2.5z" />
      <path d="M5 13.5h5.6a1.5 1.5 0 0 0 1.47-1.2l.8-4A1.5 1.5 0 0 0 11.4 6.5H9l.45-2.45A1.4 1.4 0 0 0 8.1 2.4L5 7.25" />
    </Icon>
  );
}

export function ThumbDownIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <g transform="rotate(180 8 8)">
        <path d="M2.5 7.25h2.5v6.25h-2.5z" />
        <path d="M5 13.5h5.6a1.5 1.5 0 0 0 1.47-1.2l.8-4A1.5 1.5 0 0 0 11.4 6.5H9l.45-2.45A1.4 1.4 0 0 0 8.1 2.4L5 7.25" />
      </g>
    </Icon>
  );
}

// Three sliders: settings.
export function SlidersIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" />
      <circle cx="5.5" cy="4.5" r="1.4" fill="var(--surface)" />
      <circle cx="10.5" cy="8" r="1.4" fill="var(--surface)" />
      <circle cx="7" cy="11.5" r="1.4" fill="var(--surface)" />
    </Icon>
  );
}

// A clock: the history.
export function ClockIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 4.75V8l2.25 1.5" />
    </Icon>
  );
}

// A window with a panel down its left side: the sidebar, folded or not.
export function SidebarIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="2" y="2.75" width="12" height="10.5" rx="1.75" />
      <path d="M6 2.75v10.5" />
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

// ---- The How it works page: the steps, the agents and their tools ----

export function FlowIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="3.5" cy="4" r="1.75" />
      <circle cx="12.5" cy="4" r="1.75" />
      <circle cx="8" cy="12.25" r="1.75" />
      <path d="M5.25 4h5.5M4.4 5.5l2.7 5.1M11.6 5.5l-2.7 5.1" />
    </Icon>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="5.25" r="2.75" />
      <path d="M2.75 14c.6-2.9 2.7-4.5 5.25-4.5s4.65 1.6 5.25 4.5" />
    </Icon>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.4 10.4 3.35 3.35" />
    </Icon>
  );
}

export function GlobeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M1.75 8h12.5M8 1.75c1.7 1.75 2.55 3.85 2.55 6.25S9.7 12.5 8 14.25C6.3 12.5 5.45 10.4 5.45 8S6.3 3.5 8 1.75Z" />
    </Icon>
  );
}

export function MegaphoneIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.25 6.5v3h2.5l5.5 3V3.5l-5.5 3h-2.5Z" />
      <path d="m4.75 9.5.9 3.5h1.6M12.25 6.25c.6.5.9 1.1.9 1.75s-.3 1.25-.9 1.75" />
    </Icon>
  );
}

export function ChartIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.25 13.75h11.5M4 13.75v-4M7.25 13.75V5.5M10.5 13.75V8M13.25 3.5l-3 2.25-2.5-1.5L4 7" />
    </Icon>
  );
}

export function ChipIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="4" y="4" width="8" height="8" rx="1.25" />
      <path d="M6.5 6.5h3v3h-3zM6 1.75V4M10 1.75V4M6 12v2.25M10 12v2.25M1.75 6H4M1.75 10H4M12 6h2.25M12 10h2.25" />
    </Icon>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 1.75 13.25 3.75v3.9c0 3.05-2.1 5.5-5.25 6.6-3.15-1.1-5.25-3.55-5.25-6.6v-3.9Z" />
      <path d="m5.75 8 1.6 1.6L10.5 6.5" />
    </Icon>
  );
}

export function ScaleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 2v11.75M5 13.75h6M3.5 4.25h9M3.5 4.25 1.75 9h3.5L3.5 4.25ZM12.5 4.25 10.75 9h3.5L12.5 4.25Z" />
    </Icon>
  );
}

export function SwapIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 5h10.25M10.25 2.5 12.75 5l-2.5 2.5M13.5 11H3.25M5.75 8.5 3.25 11l2.5 2.5" />
    </Icon>
  );
}

export function GavelIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m7.25 3.25 4 4M5.5 5 9.5 9M6.4 4.1l3.5 3.5M8.4 7.6 13.5 12.7M2.25 14h6" />
      <path d="m5.25 2.75 3.25-.75.75.75-.75 3.25" />
    </Icon>
  );
}

export function PulseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M1.75 8.5h2.75l1.5-4 2.75 8 1.75-4.5h3.75" />
    </Icon>
  );
}

export function WindowIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="1.75" y="2.75" width="12.5" height="10.5" rx="1.5" />
      <path d="M1.75 5.75h12.5M4 4.25h.01M5.75 4.25h.01" />
    </Icon>
  );
}

export function ServerIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="2" y="2.25" width="12" height="4.75" rx="1.25" />
      <rect x="2" y="9" width="12" height="4.75" rx="1.25" />
      <path d="M4.75 4.6h.01M4.75 11.4h.01M7.25 4.6h4M7.25 11.4h4" />
    </Icon>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="2.75" />
      <path d="M8 1.5v1.25M8 13.25v1.25M1.5 8h1.25M13.25 8h1.25M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9" />
    </Icon>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M13.25 9.6A5.5 5.5 0 0 1 6.4 2.75a5.5 5.5 0 1 0 6.85 6.85Z" />
    </Icon>
  );
}

export function MonitorIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="1.75" y="2.5" width="12.5" height="8.5" rx="1.25" />
      <path d="M6 13.75h4M8 11v2.75" />
    </Icon>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.75 4.25h10.5M6.25 4.25V2.75h3.5v1.5M4 4.25l.7 9h6.6l.7-9M6.6 6.75v4.5M9.4 6.75v4.5" />
    </Icon>
  );
}

// The Chief of Staff: the hub the four specialists report to.
export function ChiefIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="2.4" />
      <path d="M8 4.1v1.5M8 10.4v1.5M4.1 8h1.5M10.4 8h1.5" />
      <g fill="currentColor" stroke="none">
        <circle cx="8" cy="2.4" r="1.15" />
        <circle cx="13.6" cy="8" r="1.15" />
        <circle cx="8" cy="13.6" r="1.15" />
        <circle cx="2.4" cy="8" r="1.15" />
      </g>
    </Icon>
  );
}

export function TeamIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="6" cy="5.25" r="2.25" />
      <path d="M1.75 13.5c.45-2.45 2.1-3.75 4.25-3.75s3.8 1.3 4.25 3.75M10.25 3.1a2.25 2.25 0 0 1 0 4.3M11.75 9.9c1.3.5 2.15 1.7 2.5 3.6" />
    </Icon>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7.25 1.75c.45 2.95 1.3 3.8 4.25 4.25-2.95.45-3.8 1.3-4.25 4.25C6.8 7.3 5.95 6.45 3 6c2.95-.45 3.8-1.3 4.25-4.25Z" />
      <path d="M12 10.25c.2 1.15.6 1.55 1.75 1.75-1.15.2-1.55.6-1.75 1.75-.2-1.15-.6-1.55-1.75-1.75 1.15-.2 1.55-.6 1.75-1.75Z" />
    </Icon>
  );
}

export function StateIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <ellipse cx="8" cy="3.75" rx="5" ry="1.75" />
      <path d="M3 3.75v8.5c0 .95 2.25 1.75 5 1.75s5-.8 5-1.75v-8.5M3 8c0 .95 2.25 1.75 5 1.75S13 8.95 13 8" />
    </Icon>
  );
}

export function HandIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M5.5 8.25V3.5a1 1 0 0 1 2 0v4M7.5 7.5V2.75a1 1 0 0 1 2 0V7.5M9.5 7.5V3.75a1 1 0 0 1 2 0v5.5c0 2.75-1.75 4.75-4.25 4.75-1.75 0-2.75-.75-3.75-2.25L2 9a1 1 0 0 1 1.6-1.2l1.9 1.95" />
    </Icon>
  );
}
