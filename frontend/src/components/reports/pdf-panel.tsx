"use client";

// The PDF pop-up's contents: on the left, the prompt that asks the team to
// revise the proposal, and the download; on the right, the document in the
// browser's own PDF viewer. The PDF is fetched again whenever the report's
// version changes.

import { useEffect, useRef, useState } from "react";

import { GuardrailNotice } from "@/components/guardrail-notice";
import { AgentAvatar, AgentStack } from "@/components/ui/agent";
import { Button, buttonClass } from "@/components/ui/button";
import { inputClass, Label } from "@/components/ui/field";
import { DownloadIcon } from "@/components/ui/icons";
import { Notice, type Tone } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import {
  ApiError,
  type GuardrailFlag,
  type PartKey,
  type Reasoning,
  type Report,
  reportPdf,
  reviseProposal,
} from "@/lib/api";
import { PART_AGENT, TEAM } from "@/lib/agents";
import { PART_AGENTS, PART_TITLES } from "@/lib/proposal";
import { proposalWait } from "@/lib/team";

type Pdf = { version: number; url: string } | { version: number; error: string };
type Message = { tone: Tone; text: string };

const PARTS = Object.keys(PART_TITLES) as PartKey[];

export function PdfPanel({
  report,
  reasoning,
  focusPrompt = false,
  onChanged,
}: {
  report: Report;
  reasoning: Reasoning | null;
  focusPrompt?: boolean;
  // Called with the revised report, or with nothing when it changed elsewhere.
  onChanged: (report: Report | null) => void;
}) {
  const [pdf, setPdf] = useState<Pdf | null>(null);
  const [part, setPart] = useState<PartKey | "whole">("whole");
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [flags, setFlags] = useState<GuardrailFlag[]>([]);
  const prompt = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (focusPrompt) prompt.current?.focus();
  }, [focusPrompt]);

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    reportPdf(report.session_id)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setPdf({ version: report.version, url });
      })
      .catch((error: Error) => {
        if (!cancelled) setPdf({ version: report.version, error: error.message });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [report.session_id, report.version]);

  async function revise(event: React.FormEvent) {
    event.preventDefault();
    if (!instruction.trim()) {
      setMessage({ tone: "warn", text: "Say what to change." });
      return;
    }
    setMessage(null);
    setFlags([]);
    setRevising(true);
    try {
      const result = await reviseProposal(
        report.session_id,
        report.version,
        instruction.trim(),
        part === "whole" ? null : part,
        reasoning,
      );
      setInstruction("");
      setFlags(result.guardrails ?? []);
      setMessage(
        result.failed.length
          ? { tone: "warn", text: `Could not revise: ${result.failed.join(", ")}. They keep their text.` }
          : { tone: "good", text: "The proposal was revised." },
      );
      onChanged(result.report);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setMessage({ tone: "warn", text: "The report changed elsewhere, so it has been reloaded. Make the request again." });
        onChanged(null);
      } else {
        setMessage({ tone: "bad", text: (error as Error).message });
      }
    } finally {
      setRevising(false);
    }
  }

  const current = pdf?.version === report.version ? pdf : null;
  const kind = report.proposal ? "investment-proposal" : "launch-report";

  return (
    <div className="grid grid-cols-1 h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[23rem_minmax(0,1fr)] lg:grid-rows-1">
      <div className="flex min-h-0 flex-col gap-5 overflow-y-auto border-b border-rule p-5 lg:border-r lg:border-b-0">
        {report.proposal ? (
          <form onSubmit={revise} aria-label="Ask the team to revise the proposal" className="space-y-5">
            <fieldset>
              <legend className="kicker">Ask the team to revise</legend>
              <div className="mt-3 space-y-0.5">
                {(["whole", ...PARTS] as const).map((key) => (
                  <label
                    key={key}
                    className={`flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 text-sm ${
                      part === key ? "bg-sunken" : "hover:bg-sunken/60"
                    }`}
                  >
                    <input
                      type="radio"
                      name="revise-part"
                      value={key}
                      checked={part === key}
                      onChange={() => setPart(key)}
                      className="mt-1 accent-[var(--primary)]"
                    />
                    {key === "whole" ? (
                      <AgentStack agents={TEAM} />
                    ) : (
                      <AgentAvatar agent={PART_AGENT[key]} size="sm" />
                    )}
                    <span>
                      <span className="block text-ink">{key === "whole" ? "The whole proposal" : PART_TITLES[key]}</span>
                      <span className="block text-xs text-ink-3">
                        {key === "whole" ? "Every agent revises its part" : PART_AGENTS[key]}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div>
              <Label htmlFor="revise-instruction">What to change</Label>
              <textarea
                ref={prompt}
                id="revise-instruction"
                rows={4}
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="Make the year-one figures more conservative, and add a referral channel."
                className={`${inputClass} leading-relaxed`}
              />
            </div>
            <Button type="submit" variant="primary" disabled={revising} className="w-full">
              Revise
            </Button>
          </form>
        ) : (
          <p className="text-sm leading-relaxed text-ink-2">
            This is the team&apos;s report. Write the investment proposal to get the full document with charts, and to
            ask the team for changes here.
          </p>
        )}
        {revising && (
          <Progress
            title={part === "whole" ? "Every agent is revising its part." : `The ${PART_AGENTS[part]} is revising its part.`}
            wait={proposalWait(reasoning)}
            stages={[
              part === "whole" ? "Each agent applies your instruction to its part" : `The ${PART_TITLES[part]} part is rewritten`,
              "The parts built on it are brought into line",
              "The PDF is drawn again",
            ]}
          />
        )}
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <GuardrailNotice flags={flags} />
        {current && "url" in current && (
          <a
            href={current.url}
            download={`${kind}-${report.session_id.slice(0, 8)}.pdf`}
            className={buttonClass("secondary", "md", "mt-auto")}
          >
            <DownloadIcon />
            Download PDF
          </a>
        )}
      </div>
      <div className="flex min-h-[60dvh] bg-sunken lg:min-h-0">
        {!current && <p className="m-auto text-sm text-ink-3">Drawing the PDF…</p>}
        {current && "error" in current && (
          <Notice tone="bad" className="m-auto max-w-md">
            The PDF could not be made. {current.error}
          </Notice>
        )}
        {current && "url" in current && (
          <iframe src={current.url} title="The report as a PDF" className="h-full min-h-[60dvh] w-full border-0 lg:min-h-0" />
        )}
      </div>
    </div>
  );
}
