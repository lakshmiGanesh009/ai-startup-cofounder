"use client";

// The diagrams behind the How it works page, drawn by Mermaid in the browser:
// the graph LangGraph runs, how the data moves from the brief to the memo, and
// the routes the Chief of Staff's decisions take. Mermaid is loaded only when a
// diagram is shown, and draws in the page's own colours: each part in the
// colours of the agent it belongs to, with a legend beneath.

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Tabs } from "@/components/ui/tabs";
import { AGENTS, agentClass, SPECIALIST_AGENTS } from "@/lib/agents";
import type { Pipeline } from "@/lib/api";
import {
  decisionsDiagram,
  DIAGRAM_ROLES,
  type DiagramRole,
  FLOW_ROLES,
  flowDiagram,
  graphDiagram,
  type Palette,
} from "@/lib/how";
import { useDark } from "@/lib/use-theme";

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Mermaid's colours from the page's tokens, so a diagram suits light and dark;
// a token with no value is left to Mermaid's own default.
function themeVariables(): Record<string, string> {
  const [surface, sunken, paper, ink, ink2, ink3, rule, primary, soft] = [
    "--surface", "--sunken", "--paper", "--ink", "--ink-2", "--ink-3", "--rule-strong", "--primary", "--primary-soft",
  ].map(token);
  const colours: Record<string, string> = {
    background: surface,
    mainBkg: surface,
    primaryColor: surface,
    primaryBorderColor: rule,
    primaryTextColor: ink,
    secondaryColor: sunken,
    tertiaryColor: paper,
    nodeBorder: rule,
    lineColor: ink3,
    textColor: ink,
    edgeLabelBackground: paper,
    clusterBkg: sunken,
    actorBkg: surface,
    actorBorder: rule,
    actorTextColor: ink,
    actorLineColor: ink3,
    signalColor: ink2,
    signalTextColor: ink,
    labelBoxBkgColor: sunken,
    labelBoxBorderColor: rule,
    labelTextColor: ink,
    loopTextColor: ink2,
    noteBkgColor: soft,
    noteBorderColor: rule,
    noteTextColor: ink,
    activationBkgColor: soft,
    activationBorderColor: primary,
    sequenceNumberColor: surface,
  };
  const set = Object.fromEntries(Object.entries(colours).filter(([, value]) => value));
  return { ...set, fontSize: "14px" };
}

// A hex colour mixed into another at `share` (0 to 1): an agent's tint on the surface.
function mix(colour: string, onto: string, share: number): string {
  const rgb = (hex: string) => [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));
  if (!/^#[0-9a-f]{6}$/i.test(colour) || !/^#[0-9a-f]{6}$/i.test(onto)) return onto || colour;
  const [a, b] = [rgb(colour), rgb(onto)];
  return `#${a.map((value, at) => Math.round(value * share + b[at] * (1 - share)).toString(16).padStart(2, "0")).join("")}`;
}

// Each role's colours from the page's tokens (globals.css), for the theme the page is in now.
function palette(): Palette {
  const surface = token("--surface");
  const tint = parseFloat(token("--agent-tint")) / 100 || 0.14;
  const agent = (key: string) => ({ line: token(`--agent-${key}`), fill: mix(token(`--agent-${key}`), surface, tint) });
  const roles = Object.fromEntries(
    [...TEAM_COLOURS, "chief", "research"].map((key) => [key, agent(key)]),
  ) as Record<DiagramRole, { line: string; fill: string }>;
  roles.you = { line: token("--primary"), fill: token("--primary-soft") };
  roles.team = { line: token("--ink-3"), fill: token("--sunken") };
  return { roles, ink: token("--ink"), muted: token("--ink-3"), surface };
}

const TEAM_COLOURS = SPECIALIST_AGENTS as string[];

// What Mermaid cannot draw itself, applied to the drawing it returns: the four
// specialists together in all four colours (a gradient across a box), each
// participant of a sequence in its role's colours, a dotted edge dotted all
// along (Mermaid draws one that hops over another as one long dash), and with
// `backwards`, the arrowhead of each edge drawn without one (an edge back up
// the graph, written the other way round: lib/how.ts) at its start, pointing back.
function paint(svg: string, colours: Palette, backwards = false): string {
  const document = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = document.documentElement;
  if (root.nodeName !== "svg") return svg;
  const id = `${root.id || "diagram"}-team`;
  const space = "http://www.w3.org/2000/svg";
  const defs = root.querySelector("defs") ?? root.insertBefore(document.createElementNS(space, "defs"), root.firstChild);
  for (const [suffix, part] of [["line", "line"], ["fill", "fill"]] as const) {
    const gradient = document.createElementNS(space, "linearGradient");
    gradient.setAttribute("id", `${id}-${suffix}`);
    TEAM_COLOURS.forEach((key, index) => {
      const stop = document.createElementNS(space, "stop");
      stop.setAttribute("offset", `${(index / (TEAM_COLOURS.length - 1)) * 100}%`);
      stop.setAttribute("stop-color", colours.roles[key as DiagramRole][part]);
      gradient.appendChild(stop);
    });
    defs.appendChild(gradient);
  }
  const team = `fill:url(#${id}-fill);stroke:url(#${id}-line);stroke-width:2px`;
  for (const shape of root.querySelectorAll(".node.team rect, .node.team polygon, .node.team path")) {
    shape.setAttribute("style", team);
  }
  for (const actor of root.querySelectorAll("rect.actor[name]")) {
    const role = FLOW_ROLES[actor.getAttribute("name") ?? ""];
    if (!role) continue;
    const { line, fill } = colours.roles[role];
    actor.setAttribute("style", role === "team" ? team : `fill:${fill};stroke:${line};stroke-width:2px`);
  }
  for (const edge of root.querySelectorAll("path.flowchart-link")) {
    const pattern = edge.getAttribute("class")?.split(" ").find((name) => name.startsWith("edge-pattern-"));
    if (pattern === "edge-pattern-dotted") edge.setAttribute("style", `${edge.getAttribute("style") ?? ""};stroke-dasharray:3 3`);
  }
  if (backwards) {
    for (const edge of root.querySelectorAll("path.flowchart-link:not([marker-end])")) {
      const colour = edge.getAttribute("style")?.match(/stroke:(#[0-9a-f]{6})/i)?.[1].toLowerCase();
      const arrowhead =
        root.querySelector(`marker[id$="flowchart-v2-pointEnd-margin__${colour?.slice(1)}"]`) ??
        root.querySelector('marker[id$="flowchart-v2-pointEnd-margin"]');
      if (!arrowhead) continue;
      const id = `${arrowhead.id}-back`;
      if (!root.querySelector(`marker[id="${id}"]`)) {
        const back = arrowhead.cloneNode(true) as Element;
        back.setAttribute("id", id);
        back.setAttribute("orient", "auto-start-reverse");
        arrowhead.parentNode!.appendChild(back);
      }
      edge.setAttribute("marker-start", `url(#${id})`);
    }
  }
  return new XMLSerializer().serializeToString(root);
}

type Mermaid = (typeof import("mermaid"))["default"];

// Mermaid is loaded once, and draws one diagram at a time: it keeps state of
// its own while it draws. Each drawing gets an id of its own, because Mermaid
// first removes whatever element has the id it is given.
let loading: Promise<Mermaid> | null = null;
let queue: Promise<unknown> = Promise.resolve();
let drawings = 0;

function draw(source: string): Promise<string> {
  loading ??= import("mermaid").then(({ default: mermaid }) => mermaid);
  const id = `diagram-${++drawings}`;
  const job = queue.then(async () => {
    const mermaid = await loading!;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      fontFamily: token("--font-geist-sans") || "sans-serif",
      themeVariables: themeVariables(),
    });
    return (await mermaid.render(id, source)).svg;
  });
  queue = job.catch(() => undefined);
  return job;
}

// The colours a diagram uses, named, under it.
const LEGEND: { role: DiagramRole; name: string }[] = [
  { role: "you", name: "You and the app" },
  { role: "chief", name: AGENTS.chief.name },
  ...(SPECIALIST_AGENTS.map((key) => ({ role: key, name: AGENTS[key].short })) as { role: DiagramRole; name: string }[]),
  { role: "team", name: "The specialists together" },
  { role: "research", name: "Web research" },
];

export function Legend({ roles }: { roles: DiagramRole[] }) {
  return (
    <ul aria-label="Colours" className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2">
      {LEGEND.filter(({ role }) => roles.includes(role)).map(({ role, name }) => (
        <li key={role} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className={`size-3 rounded-[3px] border-2 ${
              role === "team"
                ? "team-swatch"
                : role === "you"
                  ? "border-primary bg-primary-soft"
                  : `${agentClass(role)} border-agent bg-agent-soft`
            }`}
          />
          {name}
        </li>
      ))}
    </ul>
  );
}

// A diagram's colours are fixed when it is drawn, so it is drawn again, from
// the page's tokens, when the page turns light or dark (useDark).
export function useDiagram(build: (palette: Palette) => string, backwards = false) {
  const dark = useDark();
  const [drawn, setDrawn] = useState<{ source: string; svg: string } | null>(null);
  const [failed, setFailed] = useState<{ source: string; problem: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const colours = palette();
    const source = build(colours);
    draw(source)
      .then((svg) => {
        if (!cancelled) setDrawn({ source, svg: paint(svg, colours, backwards) });
      })
      .catch((error: Error) => {
        if (!cancelled) setFailed({ source, problem: error.message || "Mermaid could not read it" });
      });
    return () => {
      cancelled = true;
    };
  }, [build, dark, backwards]);

  return { svg: drawn?.svg ?? null, source: drawn?.source ?? failed?.source ?? "", problem: failed?.problem ?? null };
}

export function MermaidDiagram({
  build,
  label,
  roles = DIAGRAM_ROLES,
  backwards = false,
}: {
  build: (palette: Palette) => string;
  label: string;
  roles?: DiagramRole[];
  backwards?: boolean;
}) {
  const { svg, source, problem } = useDiagram(build, backwards);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <figure aria-label={label} className="space-y-4">
      {svg ? (
        // Mermaid sanitises what it draws (securityLevel "strict"); the source is the app's own.
        <div className="relative diagram overflow-x-auto rounded-lg border border-rule bg-surface p-4" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : problem ? (
        <Notice tone="warn">The diagram could not be drawn ({problem}). Its Mermaid source is below.</Notice>
      ) : (
        <p className="py-16 text-center text-sm text-ink-3">Drawing the diagram…</p>
      )}
      <Legend roles={roles} />
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={copy}>
          {copied ? "Copied" : "Copy the Mermaid source"}
        </Button>
        <details className="text-sm text-ink-2">
          <summary className="cursor-pointer">Show the source</summary>
          <pre className="relative mt-2 max-w-full overflow-x-auto rounded-md bg-sunken p-3 font-mono text-xs leading-relaxed">{source}</pre>
        </details>
      </div>
    </figure>
  );
}

export function Diagrams({ pipeline }: { pipeline: Pipeline }) {
  // Made once, so a diagram is drawn again only when the page changes theme.
  const [builds] = useState(() => ({
    graph: (colours: Palette) => graphDiagram(pipeline.mermaid, colours),
    flow: (colours: Palette) => flowDiagram(pipeline.rules, colours),
    decisions: (colours: Palette) => decisionsDiagram(pipeline.rules, colours),
  }));
  return (
    <div className="h-full overflow-y-auto px-5 py-4">
      <Tabs
        label="Diagrams"
        tabs={[
          {
            label: "The graph",
            content: (
              <div className="space-y-3">
                <p className="max-w-3xl text-sm leading-relaxed text-ink-2">
                  The LangGraph state machine, drawn from the compiled graph itself. Each step is in the colours of the
                  agent that runs it, and each arrow in the colour of the step it leaves. Solid arrows always run; dotted
                  ones are the routes the Chief of Staff&apos;s decisions choose between.
                </p>
                <MermaidDiagram label="The LangGraph state machine" build={builds.graph} backwards />
              </div>
            ),
          },
          {
            label: "How data flows",
            content: (
              <div className="space-y-3">
                <p className="max-w-3xl text-sm leading-relaxed text-ink-2">
                  From your brief to the memo: what each part sends, and what comes back. Each stretch of the work is on a
                  band in the colour of who does it.
                </p>
                <MermaidDiagram
                  label="How data flows"
                  build={builds.flow}
                  roles={["you", "chief", "team", "research"]}
                />
              </div>
            ),
          },
          {
            label: "How decisions are made",
            content: (
              <div className="space-y-3">
                <p className="max-w-3xl text-sm leading-relaxed text-ink-2">
                  The routes through the graph, and what decides each one.
                </p>
                <MermaidDiagram label="How decisions are made" build={builds.decisions} />
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
