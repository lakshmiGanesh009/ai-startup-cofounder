"use client";

// The diagrams behind the How it works page, drawn by Mermaid in the browser:
// the graph exactly as LangGraph draws it, how the data moves from the brief to
// the memo, and the routes the Chief of Staff's decisions take. Mermaid is
// loaded only when a diagram is shown, and drawn in the page's own colours.

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Tabs } from "@/components/ui/tabs";
import type { Pipeline } from "@/lib/api";
import { decisionsDiagram, flowDiagram } from "@/lib/how";
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

// A diagram's colours are fixed when it is drawn, so it is drawn again when
// the page turns light or dark (useDark).

export function MermaidDiagram({ source, label }: { source: string; label: string }) {
  const dark = useDark();
  const [drawn, setDrawn] = useState<{ source: string; svg: string } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    draw(source)
      .then((svg) => {
        if (!cancelled) setDrawn({ source, svg });
      })
      .catch((error: Error) => {
        if (!cancelled) setFailed(error.message || "Mermaid could not read it");
      });
    return () => {
      cancelled = true;
    };
  }, [source, dark]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const svg = drawn?.source === source ? drawn.svg : null;
  return (
    <figure aria-label={label} className="space-y-4">
      {svg ? (
        // Mermaid sanitises what it draws (securityLevel "strict"); the source is the app's own.
        <div className="relative diagram overflow-x-auto rounded-lg border border-rule bg-surface p-4" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : failed ? (
        <Notice tone="warn">The diagram could not be drawn ({failed}). Its Mermaid source is below.</Notice>
      ) : (
        <p className="py-16 text-center text-sm text-ink-3">Drawing the diagram…</p>
      )}
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
                  The LangGraph state machine, drawn from the compiled graph itself. Solid arrows always run; dotted ones
                  are the routes the Chief of Staff&apos;s decisions choose between.
                </p>
                <MermaidDiagram label="The LangGraph state machine" source={pipeline.mermaid} />
              </div>
            ),
          },
          {
            label: "How data flows",
            content: (
              <div className="space-y-3">
                <p className="max-w-3xl text-sm leading-relaxed text-ink-2">
                  From your brief to the memo: what each part sends, and what comes back.
                </p>
                <MermaidDiagram label="How data flows" source={flowDiagram(pipeline.rules)} />
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
                <MermaidDiagram label="How decisions are made" source={decisionsDiagram(pipeline.rules)} />
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
