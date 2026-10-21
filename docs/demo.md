# Demo walkthrough

A script for the live walkthrough of a startup evaluation and an iterative
refinement, and a recorded run of both for anyone who cannot watch it live.

## Before you start

- Start the app with `./start.sh local` (or `./start.sh docker`) and open
  http://localhost:3000. The sidebar says **API connected** once the API answers.
- Leave **Research it and check the brief first** off. It adds web searches and a
  few minutes; turn it on only to show deep research (on Tavily it spends credits).
- An evaluation takes two to three minutes at the default reasoning, and a
  follow-up a little less. Talk through the live view while it runs.
- Keep a finished session in reserve. The **Reports** page keeps every session,
  so if the network fails mid-demo, show one from there.

## The walkthrough (about ten minutes)

1. **The design.** Open **How it works** and click **Show the diagrams**. The
   graph shows the Chief of Staff's plan, the specialists running together, the
   review loop that sends weak reports back, the cross-critique and its
   resolution, and the synthesis. Both loops are bounded, so a run always ends.
2. **Start an evaluation.** On **Evaluate**, under **Or start from an example**,
   pick **A premium AI brand studio on a small budget** and click **Evaluate**.
   It is the example built to make the agents disagree: a premium enterprise
   service, one founder, almost no budget. While it runs, the live view names
   each step: point out the plan (which agents were assigned, and which were
   left out), the specialists starting at the same time, and the look-up of
   official figures on FRED.
3. **The result.** The recommendation leads (go, go with conditions, or not yet),
   then the strategy, its claims tagged with the agent they came from. Then the
   tabs under it:
   - **Plan**: the objective and each agent's task, the delegation.
   - **Reviews**: each report's score and the Chief of Staff's feedback. A report
     scored under 4 went back to its specialist and was revised: reflection and
     self-correction.
   - **Conflicts**: who disagreed with whom, the Chief of Staff's decision and
     its reason, and who revised: conflict resolution.
   - **Run**: the calls, tokens and seconds of each step, and the parallel
     specialists: the optimisation.
4. **Iterative refinement.** The example has filled in **Follow up in this
   session** with "Refine the pricing strategy after financial review." Click
   **Send follow-up**. The Chief of Staff reassigns only the agents who own
   pricing; the others keep their reports, so the follow-up uses roughly half
   the first request's tokens. Compare the new strategy's prices and terms with
   the first's.
5. **The report.** Open **Reports**: the session as one report, which the
   founder can edit and download as a PDF.
6. **The Monitor.** On **How it works**, the **Monitor** tab shows what the API
   has done: evaluations, time to a decision, model calls, tokens and errors.

To show the same from a terminal, without the web app:

```bash
uv run python demo.py scenarios/premium_on_a_budget.json
```

It prints each stage of the first request (plan, reports, review rounds,
conflict resolutions, strategy), then the same for the follow-up.

## What each step shows

| Evaluation criterion | Where in the walkthrough |
| --- | --- |
| Multi-agent coordination quality | 2, the live view; 3, Conflicts |
| Delegation and synthesis effectiveness | 3, Plan and the strategy; 4, only the affected agents rerun |
| Reflection and self-correction capability | 3, Reviews; 4, the refinement |
| Workflow clarity and state modeling | 1, the diagrams; 4, the session kept between requests |
| System optimization and performance | 3, Run; 6, the Monitor; [performance.md](performance.md) |
| Code quality and modularity | [architecture.md](architecture.md), the tests |
| Documentation clarity | this guide, [architecture.md](architecture.md) |

## A recorded run

`demo.py scenarios/premium_on_a_budget.json` on Azure OpenAI (`gpt-5-mini`, the
default reasoning) on 21 October 2026. The two requests took 3 min 50 s together.

### The first request

The Chief of Staff assigned all four specialists, each its own task: Marketing
the buyers and three 90-day go-to-market experiments, Finance a 90-day model
with the prices and the pilots needed to break even, Technical the deliverables,
tools and time each takes, Risk the legal, IP and delivery risks with cheap
mitigations.

**Review.** All four reports passed on the first round (Marketing 4, Finance 4,
Technical 5, Risk 4), so none went back. A report scored under 4 returns to its
specialist with the feedback and is revised once.

**Critique.** The specialists disagreed three times, and the Chief of Staff
settled each, sending the specialist it overruled back to revise:

| Disagreement | Decision | Revised |
| --- | --- | --- |
| Marketing's $15k six-week pilot against Finance's $25k 30-day one | One five-week "AI Brand Sprint" at $15,000 with a 50% deposit: a solo founder with almost no budget needs a pilot that closes and delivers quickly | Finance |
| Marketing's lean $15k offer against Risk's $45k procurement-grade one, with insurance and retainers | Contract-first terms now (NDA, a short SOW, liability capped at the fee); insurance and a backup retainer only after $50k of revenue, three pilots or six months | Risk |
| Technical's five weeks and one or two pilots against Finance's 30-day delivery at $25k | Technical's delivery plan; Finance to rework its numbers for a $15k pilot with the founder's salary deferred | Finance |

**Synthesis.** "Go with conditions": the $15,000 Sprint, paid 50% on signing,
40% on delivery and 10% on approval; $2,400 of direct costs a Sprint, an 84%
gross margin; two Sprints for $30k in 90 days. Finance's revised report carries
the same figures, so the strategy and the reports agree.

### The follow-up: "Refine the pricing strategy after financial review."

The Chief of Staff reassigned only Finance and Marketing; Technical's and Risk's
reports were kept. Both passed review (Finance 5, Marketing 4), and the critique
settled three more questions:

- **The follow-on retainer.** Marketing's $5,000 a month against Finance's
  $4,000: $4,000, capped at 20 hours, the safer cash assumption. Marketing
  revised.
- **A $6,000 proof of concept** that Finance added: not offered at launch, to keep
  one simple offer until there is conversion data. Finance revised.
- **The scope.** Marketing's six-week pilot against Technical's five-week,
  broader one: six weeks with Technical's full handoff. Technical revised its
  estimates, although the follow-up had not reassigned it.

The refined strategy keeps the $15,000 Sprint, now over six weeks, adds the
$4,000 retainer as the step after a pilot, and cites official figures from FRED
for the market.
