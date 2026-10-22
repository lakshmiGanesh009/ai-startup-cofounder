"use client";

// The team at work on the graph LangGraph runs, opened from the Evaluate page's
// progress card: the graph in the agents' colours, lit up as the steps stream
// in (the step at work glowing, the arrows the work moves along running, each
// finished step ticked, or counted when it ran again), and beside it what the
// team is doing now and each turn it has taken. It stays open on the finished
// run once the team is done.

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { Legend, useDiagram } from "@/components/how/diagrams";
import { AgentAvatar, AgentStack } from "@/components/ui/agent";
import { Dialog } from "@/components/ui/dialog";
import { Notice } from "@/components/ui/notice";
import { Clock } from "@/components/ui/progress";
import { agentClass, agentsOf } from "@/lib/agents";
import { getPipeline, type Pipeline, type Step } from "@/lib/api";
import { DIAGRAM_ROLES, type GraphEdge, graphDiagram, graphEdges, graphRole, type Palette } from "@/lib/how";
import { LIVE_STATES, type LiveNode, liveEdges, liveNodes, type Turn, turns } from "@/lib/live-graph";
import { activity, actor, doing, formatSeconds, stepName } from "@/lib/team";

// The run the graph shows: the one under way, or the one that just ended.
export type Watched = { prompt: string; steps: Step[]; started: number; problem?: string };

const SVG = "http://www.w3.org/2000/svg";

// The colour a node glows in and its mark is filled with: its agent's, the
// specialists' together in ink, the founder's in the primary colour.
function colours(node: string): { glow: string; solid: string } {
  const role = graphRole(node);
  if (role === "team") return { glow: "var(--ink-3)", solid: "var(--ink-2)" };
  if (!role || role === "you") return { glow: "var(--primary)", solid: "var(--primary)" };
  return { glow: `var(--agent-${role})`, solid: `var(--agent-${role}-solid)` };
}

// The mark on a finished step: a tick, the number of times it ran, or "!" when it failed.
function mark(node: LiveNode): string | null {
  if (node.state === "failed") return "!";
  if (node.state !== "done" || node.runs === 0) return null;
  return node.runs > 1 ? `×${node.runs}` : "✓";
}

function setMark(group: SVGGElement, node: LiveNode, fill: string) {
  const text = mark(node);
  const current = group.querySelector<SVGGElement>(":scope > .live-mark");
  if (current?.dataset.mark === text) return;
  current?.remove();
  const shape = group.firstElementChild as SVGGraphicsElement | null;
  if (!text || typeof shape?.getBBox !== "function") return;
  const box = shape.getBBox();
  const place = document.createElementNS(SVG, "g");
  place.setAttribute("class", "live-mark");
  place.dataset.mark = text;
  // On the box's top right corner, half in and half out, clear of its label.
  place.setAttribute("transform", `translate(${box.x + box.width - 2}, ${box.y + 2})`);
  const badge = document.createElementNS(SVG, "g");
  badge.setAttribute("class", "live-mark-pop");
  const back = document.createElementNS(SVG, "rect");
  const width = text.length > 1 ? 34 : 24;
  for (const [name, value] of [["x", -width / 2], ["y", -12], ["width", width], ["height", 24], ["rx", 12]] as const) {
    back.setAttribute(name, String(value));
  }
  back.setAttribute("style", `fill:${node.state === "failed" ? "var(--bad)" : fill};stroke:var(--surface);stroke-width:2.5px`);
  const label = document.createElementNS(SVG, "text");
  label.setAttribute("text-anchor", "middle");
  label.setAttribute("dominant-baseline", "central");
  // No stroke: Mermaid strokes every child of a box (!important), and the mark is one.
  label.setAttribute("style", "fill:#fff;stroke:none;font-size:14px;font-weight:700");
  label.textContent = text;
  badge.append(back, label);
  place.append(badge);
  group.append(place);
}

// Lights up the drawn graph: each node's state as a class (the CSS, globals.css,
// fades, glows and dashes it) with its mark, and the edges taken and moving.
function lightUp(root: SVGSVGElement, nodes: Record<string, LiveNode>, edges: GraphEdge[], steps: Step[], live: boolean) {
  for (const group of root.querySelectorAll<SVGGElement>("g.node")) {
    const name = group.id.match(/-flowchart-(.+)-\d+$/)?.[1];
    const node = name ? nodes[name] : undefined;
    if (!name || !node) continue;
    for (const state of LIVE_STATES) group.classList.toggle(`live-${state}`, node.state === state);
    const { glow, solid } = colours(name);
    group.style.setProperty("--live", glow);
    setMark(group, node, solid);
  }
  const { taken, moving } = liveEdges(steps, edges);
  root.querySelectorAll<SVGPathElement>("path.flowchart-link").forEach((path, index) => {
    const edge = edges[index];
    // Mermaid draws the edges in the order they are written (graphEdges).
    const found = edge && path.dataset.id?.startsWith(`L_${edge.drawn[0]}_${edge.drawn[1]}_`);
    path.classList.toggle("live-taken", Boolean(found && taken.has(index)));
    path.classList.toggle("live-moving", Boolean(found && live && moving.has(index)));
    path.classList.toggle("live-back", Boolean(found && edge.drawn[0] !== edge.from));
  });
}

// Larger type and closer rows than on How it works, so the whole graph reads
// at the height of the pop-up. The directive goes after LangGraph's front matter.
const COMPACT = '%%{init: {"flowchart": {"rankSpacing": 36, "nodeSpacing": 30}, "themeVariables": {"fontSize": "17px"}}}%%';

function compact(source: string): string {
  const front = source.match(/^---\n[\s\S]*?\n---\n/)?.[0] ?? "";
  return `${front}${COMPACT}\n${source.slice(front.length)}`;
}

function LiveDiagram({ pipeline, steps, live }: { pipeline: Pipeline; steps: Step[]; live: boolean }) {
  // Made once, so the graph is drawn again only when the page changes theme.
  const [build] = useState(() => (palette: Palette) => compact(graphDiagram(pipeline.mermaid, palette)));
  const [edges] = useState(() => graphEdges(pipeline.mermaid));
  const { svg, problem } = useDiagram(build, true);
  const box = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const root = box.current?.querySelector("svg");
    if (root) lightUp(root, liveNodes(steps, live), edges, steps, live);
  }, [svg, steps, live, edges]);

  if (problem) return <Notice tone="warn">The graph could not be drawn ({problem}).</Notice>;
  if (!svg) return <p className="py-16 text-center text-sm text-ink-3">Drawing the graph…</p>;
  return (
    // Mermaid sanitises what it draws (securityLevel "strict"); the source is the app's own.
    <div
      ref={box}
      role="img"
      aria-label="The graph LangGraph runs, lit up as the team works"
      className="diagram live-graph rounded-lg border border-rule bg-surface p-4 lg:min-h-0 lg:flex-1"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

// What the graph's marks mean.
function Key() {
  const item = "flex items-center gap-1.5";
  return (
    <ul aria-label="What the graph shows" className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2">
      <li className={item}>
        <span aria-hidden className="live-key-running size-3 rounded-[3px] border-2 border-primary bg-primary-soft" />
        At work
      </li>
      <li className={item}>
        <span aria-hidden className="live-key-moving h-0.5 w-5" />
        The work moving on
      </li>
      <li className={item}>
        <span aria-hidden className="flex size-3.5 items-center justify-center rounded-full bg-ink-2 text-[8px] font-semibold text-surface">
          ✓
        </span>
        Done; ×2 when it ran again
      </li>
      <li className={item}>
        <span aria-hidden className="size-3 rounded-[3px] border-2 border-rule-strong opacity-50" />
        Still to come
      </li>
      <li className={item}>
        <span aria-hidden className="size-3 rounded-[3px] border-2 border-dashed border-rule-strong opacity-40" />
        Not needed this time
      </li>
      <li className={item}>
        <span aria-hidden className="w-5 border-t-2 border-dotted border-ink-3" />
        Dotted: a route the Chief of Staff&apos;s decisions choose
      </li>
    </ul>
  );
}

// The Chief of Staff's steps that run again in a later round; a specialist
// that runs again revises its report.
const ROUNDS = new Set(["review", "critique", "resolve"]);

// A turn's heading: the step, and who took it when that is someone else.
function TurnTitle({ turn }: { turn: Turn }) {
  const name = stepName(turn.node);
  const who = turn.done?.provider ?? actor(turn.node);
  const again = turn.run > 1 ? (ROUNDS.has(turn.node) ? ` · round ${turn.run}` : " · revision") : "";
  return (
    <span className="min-w-0">
      <span className="font-medium text-ink">
        {name}
        {again}
      </span>
      {who !== name && <span className="text-ink-3"> · {who}</span>}
    </span>
  );
}

function Turns({ steps }: { steps: Step[] }) {
  const list = turns(steps).reverse();
  if (!list.length) return <p className="mt-3 text-sm text-ink-3">The Chief of Staff is reading the brief.</p>;
  return (
    <ol className="mt-3 space-y-2">
      {list.map((turn) => {
        const agents = agentsOf(turn.node);
        const working = turn.finished === undefined;
        const failed = turn.done?.failed;
        return (
          <li
            key={`${turn.node}-${turn.run}`}
            className={`${agentClass(agents[0])} rounded-lg border px-3 py-2 text-sm ${
              failed ? "border-bad/40 bg-bad-soft" : working ? "border-agent bg-agent-soft" : "border-rule bg-surface"
            }`}
          >
            <p className="flex items-start gap-2">
              <span className="pt-0.5">
                {agents.length > 1 ? <AgentStack agents={agents} /> : <AgentAvatar agent={agents[0]} size="xs" />}
              </span>
              <TurnTitle turn={turn} />
              <time className="ml-auto shrink-0 pt-0.5 font-mono text-[11px] text-ink-3 tabular">
                {formatSeconds(turn.started)}
                {working ? "" : `–${formatSeconds(turn.finished!)}`}
              </time>
            </p>
            <p className={`mt-1 text-[13px] leading-snug ${failed ? "text-bad" : "text-ink-2"}`}>
              {working ? (
                <span className="flex items-center gap-1.5">
                  <span aria-hidden className="working-dot size-1.5 shrink-0 rounded-full bg-agent" />
                  {doing(turn.node, turn.run)}
                </span>
              ) : (
                turn.done?.summary
              )}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

// Where the run stands: what the team is doing now, or how it ended.
function Now({ run, live }: { run: Watched; live: boolean }) {
  const last = run.steps.at(-1)?.at ?? 0;
  const finished = run.steps.some((step) => step.type === "done" && step.node === "synthesis");
  const ending = run.problem
    ? `The run stopped: ${run.problem}`
    : finished
      ? "The launch strategy is ready. Close this to read it."
      : "The run ended.";
  return (
    <section aria-label="What the team is doing">
      <div className="flex items-center gap-3">
        <p className="kicker flex items-center gap-2">
          {live && <span aria-hidden className="working-dot size-2 rounded-full bg-primary" />}
          {live ? "Now" : "Finished"}
        </p>
        {live ? (
          <Clock className="ml-auto" since={run.started} />
        ) : (
          <span className="ml-auto font-mono text-sm text-ink-2 tabular">{formatSeconds(last)}</span>
        )}
      </div>
      <p aria-live="polite" className={`mt-2 text-[15px] leading-snug ${run.problem ? "text-bad" : "text-ink"}`}>
        {live ? activity(run.steps) : ending}
      </p>
    </section>
  );
}

export function LiveGraph({
  open,
  run,
  live,
  onClose,
}: {
  open: boolean;
  run: Watched | null;
  live: boolean;
  onClose: () => void;
}) {
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const turnsHeading = useId();

  // The graph is asked for the first time it is opened.
  useEffect(() => {
    if (!open || pipeline) return;
    getPipeline()
      .then((answer) => {
        setPipeline(answer);
        setProblem(null);
      })
      .catch((error: Error) => setProblem(error.message));
  }, [open, pipeline]);

  return (
    <Dialog open={open && run !== null} title="The team at work, on the graph" description={run?.prompt} onClose={onClose}>
      {run && (
        <div className="flex h-full min-h-0 flex-col overflow-y-auto lg:grid lg:grid-cols-[minmax(0,1fr)_24rem] lg:overflow-hidden">
          {/* On a large screen the graph fills the column's height, the key and colours beneath it. */}
          <div className="order-2 space-y-4 p-5 lg:col-start-1 lg:row-start-1 lg:flex lg:min-h-0 lg:flex-col lg:gap-4 lg:space-y-0">
            {pipeline ? (
              <LiveDiagram pipeline={pipeline} steps={run.steps} live={live} />
            ) : problem ? (
              <Notice tone="bad">{problem} The graph comes from the API, so it needs the API running.</Notice>
            ) : (
              <p className="py-16 text-center text-sm text-ink-3">Asking the API for the graph…</p>
            )}
            <div className="space-y-2 lg:shrink-0">
              <Key />
              <Legend roles={DIAGRAM_ROLES} />
            </div>
          </div>
          {/* On a phone: what the team is doing on top, the graph, then the turns. */}
          <div className="contents lg:col-start-2 lg:row-start-1 lg:block lg:min-h-0 lg:overflow-y-auto lg:border-l lg:border-rule lg:bg-sunken/40">
            <div className="sticky top-0 z-10 order-1 border-b border-rule bg-surface p-5 lg:static lg:border-b-0 lg:bg-transparent lg:pb-2">
              <Now run={run} live={live} />
            </div>
            <section aria-labelledby={turnsHeading} className="order-3 border-t border-rule p-5 lg:border-t-0">
              <h3 id={turnsHeading} className="kicker">
                Step by step, newest first
              </h3>
              <Turns steps={run.steps} />
            </section>
          </div>
        </div>
      )}
    </Dialog>
  );
}
