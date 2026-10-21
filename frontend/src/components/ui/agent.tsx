// The agents as the UI draws them: an avatar in the agent's colour with its
// icon, an avatar with the name beside it, a stack of avatars for a step
// several agents share, and the team's colours in a row. The avatars are
// hidden from screen readers; the name beside them, or the control they sit
// in, says who.

import {
  ChartIcon,
  ChiefIcon,
  ChipIcon,
  GlobeIcon,
  MegaphoneIcon,
  ShieldIcon,
} from "@/components/ui/icons";
import { AGENTS, type AgentKey, agentClass, TEAM } from "@/lib/agents";

const ICONS: Record<AgentKey, (props: { className?: string }) => React.ReactNode> = {
  chief: ChiefIcon,
  marketing: MegaphoneIcon,
  finance: ChartIcon,
  technical: ChipIcon,
  risk: ShieldIcon,
  research: GlobeIcon,
};

const SIZES = {
  xs: { box: "size-5", icon: "size-3" },
  sm: { box: "size-6", icon: "size-3.5" },
  md: { box: "size-8", icon: "size-4" },
  lg: { box: "size-11", icon: "size-[18px]" },
};

export type AvatarSize = keyof typeof SIZES;

export function AgentIcon({ agent, className }: { agent: AgentKey; className?: string }) {
  const Glyph = ICONS[agent];
  return <Glyph className={className} />;
}

// The agent's icon on its tint, in a ring of its colour; `solid` for the agent
// at the centre of attention, filled with its colour.
export function AgentAvatar({
  agent,
  size = "sm",
  solid = false,
  className = "",
}: {
  agent: AgentKey;
  size?: AvatarSize;
  solid?: boolean;
  className?: string;
}) {
  const { box, icon } = SIZES[size];
  return (
    <span
      aria-hidden
      title={AGENTS[agent].name}
      className={`${agentClass(agent)} inline-flex ${box} shrink-0 items-center justify-center rounded-full ${
        solid ? "bg-agent-solid text-white" :"bg-agent-soft text-agent-deep shadow-[inset_0_0_0_1px_var(--agent-line)]"
      } ${className}`}
    >
      <AgentIcon agent={agent} className={icon} />
    </span>
  );
}

// Several agents at once, overlapping: the specialists writing, say.
export function AgentStack({ agents, size = "xs" }: { agents: AgentKey[]; size?: AvatarSize }) {
  return (
    <span className="inline-flex items-center -space-x-1.5">
      {agents.map((agent) => (
        <span key={agent} className="rounded-full bg-paper p-px">
          <AgentAvatar agent={agent} size={size} />
        </span>
      ))}
    </span>
  );
}

// An agent's avatar and name; the name in ink, the colour beside it.
export function AgentName({
  agent,
  size = "xs",
  children,
  className = "",
}: {
  agent: AgentKey;
  size?: AvatarSize;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={`inline-flex min-w-0 items-center gap-2 ${className}`}>
      <AgentAvatar agent={agent} size={size} />
      <span className="min-w-0">{children ?? AGENTS[agent].name}</span>
    </span>
  );
}

// The team's colours in a row: the Chief of Staff, then the specialists.
export function TeamStripe({ className = "" }: { className?: string }) {
  return (
    <span aria-hidden className={`flex gap-[3px] ${className}`}>
      {TEAM.map((agent) => (
        <span key={agent} className={`${agentClass(agent)} h-[3px] w-5 rounded-full bg-agent`} />
      ))}
    </span>
  );
}
