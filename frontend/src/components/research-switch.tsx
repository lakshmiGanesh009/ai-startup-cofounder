"use client";

// Where web research runs, for the brief's research and the specialists' deep
// research: Azure OpenAI's own web search, the default, or Tavily, for
// demanding tasks. A provider the server has not set up cannot be chosen. The
// choice is remembered in this browser.

import { PROVIDER_NAMES, RESEARCH_PROVIDERS, type ResearchProvider } from "@/lib/api";
import { useBackend } from "@/lib/backend";

const NOTES: Record<ResearchProvider, string> = {
  azure: "Bing search through your Azure OpenAI deployment: quick, and billed to Azure per search.",
  tavily: "Deeper research for demanding tasks, from your Tavily credits.",
};

export function ResearchSwitch() {
  const { status, health, researchProvider, setResearchProvider } = useBackend();
  const ready = health?.research.providers;

  let note = "Shown once the backend answers.";
  if (status === "up" && researchProvider) {
    note = NOTES[researchProvider];
    if (researchProvider === "azure" && ready && !ready.tavily) note += " Add a TAVILY_API_KEY to use Tavily.";
  } else if (status === "up") {
    note = "No web research: set up Azure OpenAI, or add a TAVILY_API_KEY.";
  }

  return (
    <fieldset>
      <legend className="kicker">Web research</legend>
      <div className="mt-3 grid grid-cols-2 gap-0.5 rounded-md border border-rule-strong bg-sunken p-0.5">
        {RESEARCH_PROVIDERS.map((provider) => (
          <label
            key={provider}
            className="flex cursor-pointer items-center justify-center rounded-[5px] px-1.5 py-1.5 text-[12.5px] whitespace-nowrap text-ink-2 transition-colors hover:text-ink has-[:checked]:bg-surface has-[:checked]:font-medium has-[:checked]:text-ink has-[:checked]:shadow-[0_1px_2px_rgb(0_0_0/0.08)] has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-45 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-focus"
          >
            <input
              type="radio"
              name="research-provider"
              value={provider}
              checked={researchProvider === provider}
              disabled={!ready?.[provider]}
              onChange={() => setResearchProvider(provider)}
              aria-describedby="research-note"
              className="sr-only"
            />
            {PROVIDER_NAMES[provider]}
          </label>
        ))}
      </div>
      <p id="research-note" className="mt-2 text-xs leading-relaxed text-ink-3">
        {note}
      </p>
    </fieldset>
  );
}
