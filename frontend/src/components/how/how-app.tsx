"use client";

// The How it works page: how the founding team turns a brief into a decision,
// in pictures and plain words, with the diagrams behind it drawn from the
// running code; and the Monitor, what the API has been doing.

import { useEffect, useState } from "react";

import { Diagrams } from "@/components/how/diagrams";
import {
  CritiqueSection,
  DecisionsSection,
  JudgementSection,
  ResearchSection,
  StackSection,
  StateSection,
  TeamSection,
  UserFlowSection,
} from "@/components/how/explainer";
import { MonitorView } from "@/components/how/monitor-view";
import { PipelineMap } from "@/components/how/pipeline-map";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { FlowIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { getPipeline, type Pipeline } from "@/lib/api";
import { useBackend } from "@/lib/backend";
import { STATIONS } from "@/lib/how";

const DESCRIPTION =
  "How the founding team turns your brief into a decision: the agents, the pipeline, how the Chief of Staff decides, the stack, and where your judgement comes in. The Monitor shows what the API has been doing.";

export function HowItWorks() {
  const { reasoning } = useBackend();
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [diagrams, setDiagrams] = useState(false);
  const [tab, setTab] = useState(0);

  useEffect(() => {
    getPipeline()
      .then(setPipeline)
      .catch((error: Error) => setProblem(error.message));
  }, []);

  return (
    <div>
      <PageHeader title="How it works" description={DESCRIPTION} />
      {problem && (
        <Notice tone="bad" className="mt-8">
          {problem} The page asks the API how the pipeline is set up, so it needs the API running.
        </Notice>
      )}
      <div className="mt-8">
        <Tabs
          label="How it works"
          onSelect={setTab}
          tabs={[
            {
              label: "The pipeline",
              content: pipeline ? (
                <div className="space-y-14">
                  <section aria-labelledby="gist-title">
                    <p className="kicker">In a gist</p>
                    <h2 id="gist-title" className="mt-1 font-serif text-[1.6rem] leading-tight font-medium tracking-[-0.01em]">
                      From a brief to a decision, in {STATIONS.length} steps
                    </h2>
                    <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-ink-2">
                      You write the brief. The Chief of Staff, the orchestrator, plans the work; four specialists research
                      and write at the same time; the Chief of Staff checks every report against a rubric; the
                      specialists cross-check each other; the Chief of Staff settles their conflicts and writes the
                      strategy. Each step reads from one shared state and writes its part back. Select a step to read
                      how it works.
                    </p>
                    <div className="mt-8">
                      <PipelineMap />
                    </div>
                    <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-rule bg-surface px-5 py-4">
                      <p className="grow basis-80 text-sm text-ink-2">
                        See the real graph LangGraph runs, how the data flows from your brief to the memo, and the routes
                        the Chief of Staff&apos;s decisions take.
                      </p>
                      <Button variant="primary" onClick={() => setDiagrams(true)}>
                        <FlowIcon />
                        Show the diagrams
                      </Button>
                    </div>
                  </section>
                  <TeamSection pipeline={pipeline} reasoning={reasoning} />
                  <DecisionsSection pipeline={pipeline} />
                  <StateSection />
                  <CritiqueSection pipeline={pipeline} />
                  <ResearchSection pipeline={pipeline} />
                  <JudgementSection />
                  <StackSection />
                  <UserFlowSection />
                </div>
              ) : (
                !problem && <p className="py-10 text-sm text-ink-3">Asking the API how the pipeline is set up…</p>
              ),
            },
            { label: "Monitor", content: <MonitorView active={tab === 1} /> },
          ]}
        />
      </div>
      {pipeline && (
        <Dialog
          open={diagrams}
          title="Diagrams"
          description="Drawn with Mermaid from the running code"
          onClose={() => setDiagrams(false)}
        >
          <Diagrams pipeline={pipeline} />
        </Dialog>
      )}
    </div>
  );
}
