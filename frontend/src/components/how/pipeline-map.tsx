// The pipeline at a glance: the steps from a brief to a decision, who takes
// each, what it hands on, and where the founder decides. A dot travels along
// the line to show the work moving (it stays still for reduced motion).

import { AgentIcon, AgentName } from "@/components/ui/agent";
import {
  CompassIcon,
  DocumentIcon,
  GavelIcon,
  GlobeIcon,
  HandIcon,
  ScaleIcon,
  SearchIcon,
  SwapIcon,
  UserIcon,
} from "@/components/ui/icons";
import { AGENTS, type AgentKey, agentClass, SPECIALIST_AGENTS, TEAM } from "@/lib/agents";
import { type IconName, type Station, STATIONS } from "@/lib/how";

const ICONS: Record<Exclude<IconName, "team">, (props: { className?: string }) => React.ReactNode> = {
  user: UserIcon,
  search: SearchIcon,
  compass: CompassIcon,
  globe: GlobeIcon,
  scale: ScaleIcon,
  swap: SwapIcon,
  gavel: GavelIcon,
  document: DocumentIcon,
};

// Who takes each station: one agent's colour, the specialists' together, or
// none for the founder's own steps.
const STATION_AGENTS: Record<string, AgentKey[]> = {
  prepare: ["chief"],
  plan: ["chief"],
  research: ["research"],
  reports: SPECIALIST_AGENTS,
  review: ["chief"],
  "cross-check": SPECIALIST_AGENTS,
  resolve: ["chief"],
  strategy: ["chief"],
};

// The four specialists in one circle, each in its colour.
function Team() {
  return (
    <span className="grid grid-cols-2 gap-0.5">
      {SPECIALIST_AGENTS.map((agent) => (
        <span key={agent} className={`${agentClass(agent)} text-agent-deep`}>
          <AgentIcon agent={agent} className="size-3" />
        </span>
      ))}
    </span>
  );
}

function Mark({ station }: { station: Station }) {
  const Glyph = station.icon === "team" ? null : ICONS[station.icon];
  const agents = STATION_AGENTS[station.key] ?? [];
  const single = agents.length === 1 ? agents[0] : null;
  const ring =
    agents.length > 1
      ? { background: `conic-gradient(${agents.map((a, i) => `var(--agent-${a}) ${i * 25}% ${(i + 1) * 25}%`).join(", ")})` }
      : undefined;
  return (
    <span
      className={`${single ? agentClass(single) : ""} relative z-10 flex size-11 shrink-0 items-center justify-center rounded-full ${
        ring ? "" : "border"
      } ${station.optional ? "border-dashed" : ""} ${
        single
          ? "border-agent-line bg-agent-soft text-agent-deep"
          : ring
            ? "text-ink-2"
            : "border-rule-strong bg-surface text-ink-2"
      } transition-transform group-hover:scale-105`}
      style={ring}
    >
      {ring && <span aria-hidden className="absolute inset-[2.5px] rounded-full bg-surface" />}
      <span className="relative">{Glyph ? <Glyph className="size-[18px]" /> : <Team />}</span>
      {station.yours && (
        <span
          title="Your call"
          className="absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full border border-paper bg-warn-soft text-warn"
        >
          <HandIcon className="size-3" />
        </span>
      )}
    </span>
  );
}

export function PipelineMap() {
  return (
    <figure aria-label="The pipeline, step by step">
      <ol className="relative grid grid-cols-1 gap-x-3 gap-y-5 sm:grid-cols-3 lg:grid-cols-9">
        <span aria-hidden className="pipeline-line hidden lg:block" />
        {STATIONS.map((station, index) => (
          <li key={station.key}>
            <a
              href={`#${station.more}`}
              className="group flex gap-3 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-focus lg:flex-col lg:items-center lg:text-center"
            >
              <Mark station={station} />
              <span className="min-w-0">
                <span className="block text-[11px] text-ink-3 tabular">{String(index + 1).padStart(2, "0")}</span>
                <span className="block font-medium text-ink group-hover:underline group-hover:underline-offset-4">
                  {station.title}
                </span>
                <span className="block text-xs leading-snug text-ink-3">{station.who}</span>
                <span className="mt-1.5 inline-block rounded bg-sunken px-1.5 py-0.5 font-mono text-[10.5px] leading-snug text-ink-2">
                  {station.makes}
                </span>
                {station.optional && <span className="mt-1 block text-[11px] text-ink-3 italic">optional</span>}
              </span>
            </a>
          </li>
        ))}
      </ol>
      <figcaption className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs text-ink-3">
        {[...TEAM, "research" as const].map((agent) => (
          <AgentName key={agent} agent={agent}>
            {AGENTS[agent].short}
          </AgentName>
        ))}
        <span className="flex items-center gap-2">
          <span aria-hidden className="size-3 rounded-full border border-dashed border-ink-3" /> Optional
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden className="flex size-4 items-center justify-center rounded-full bg-warn-soft text-warn">
            <HandIcon className="size-2.5" />
          </span>
          Your call
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden className="rounded bg-sunken px-1 font-mono text-[10px] text-ink-2">a · b</span> What it hands
          on
        </span>
      </figcaption>
    </figure>
  );
}
