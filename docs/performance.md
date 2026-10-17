# Performance

Every `/evaluate` response carries a `metrics` map: one entry per node, each with
the LLM `calls` it made, the wall-clock `seconds` it took, and `tokens` (summed
from the model's usage when the reply reports it). The metrics cover the current
request only, so a follow-up's numbers do not include the request before it.

## How to measure

Run the Step 9 scenarios against a real model and read the `metrics` map:

```bash
uv run python demo.py scenarios/healthcare_scheduling.json
uv run python demo.py scenarios/gtm_risk.json
uv run python demo.py scenarios/premium_on_a_budget.json
```

Record total LLM calls and total seconds per request. Baseline is the workflow
without the optimisations below; "optimised" is with them.

## What was optimised

- **No critique pass after the last allowed round.** When cross-critique sends a
  specialist back to revise and no further round is allowed
  (`MAX_CRITIQUE_ROUNDS` = 1), the revised report goes straight to synthesis.
  Before, every specialist critiqued again and every new conflict was resolved
  again, although nothing could be revised any more.
- **One resolve call per critique round.** The Chief of Staff settles all of a
  round's conflicts in one call instead of one call per conflict. Specialists
  often raise the same clash from both sides; deciding them together also keeps
  the decisions consistent.
- **Follow-ups: only the reassigned specialists critique.** Each still reads
  every other report, but the unchanged reports are not cross-checked again.
- **Short planner tasks.** The plan gives each specialist a one- or two-sentence
  task instead of a long brief. Reports, and every prompt that carries them
  (review, critique, synthesis), get shorter.
- **Skip cross-critique for a single specialist.** With one report there is
  nothing to cross-check, so the critique and resolve pass is skipped.
- **Review and critique skip unavailable reports.** A specialist whose call
  failed produces a gap marker; review and critique do not spend a call on it.
- **Single-revision cap** (`MAX_ITERATIONS`, `MAX_CRITIQUE_ROUNDS` = 1) bounds the
  review and critique loops, so a weak report costs at most one extra call.

## Baseline vs optimised

Measured on 2026-10-16 against Azure OpenAI `gpt-5-mini` (reasoning effort
`minimal`). Each scenario ran twice for each version, with the three scenarios
running at the same time; the numbers are the mean of the two runs for one
request. LLM calls and tokens were counted with a LangChain callback, so they
include structured calls (see Known gaps).

The baseline is the same workflow with the first four optimisations above
switched off. It includes the correctness fixes made alongside them, chiefly the
planner fix: the code as first merged often assigned too few specialists (one
specialist in 3 of 6 first requests), which made it look cheap while skipping
work the request needed. Comparing like with like needed both versions to
delegate the same way.

| Scenario | Request | LLM calls | Tokens | Seconds |
| --- | --- | --- | --- | --- |
| gtm_risk | first | 34.5 → 21 (−39%) | 125.0k → 72.5k (−42%) | 164 → 108 (−34%) |
| healthcare_scheduling | first | 28 → 19 (−32%) | 101.9k → 74.2k (−27%) | 144 → 116 (−19%) |
| healthcare_scheduling | follow-up | 30.5 → 11 (−64%) | 157.7k → 49.0k (−69%) | 232 → 86 (−63%) |
| premium_on_a_budget | first | 31 → 20 (−35%) | 133.1k → 73.0k (−45%) | 169 → 109 (−35%) |
| premium_on_a_budget | follow-up | 26.5 → 11 (−58%) | 129.1k → 47.9k (−63%) | 156 → 82 (−47%) |

`gtm_risk` has no follow-up. In one healthcare baseline run the planner assigned
three specialists instead of four, which lowers that baseline mean; the
improvement there is understated rather than overstated.

With the optimisations, a follow-up costs about half a first request (10–12
calls against 19–22). In the baseline a follow-up cost as much as or more than a
first request, because every report was critiqued again.

## Trade-offs

- **No critique after the last round.** A revised report is not cross-checked
  again, so a revision could introduce a new disagreement that goes unflagged.
  Synthesis still sees every report and names where they differ.
- **One resolve call per round.** One larger prompt instead of several small
  ones, and the Chief of Staff may merge two flagged conflicts into one decision.
- **Follow-up critique by the reassigned specialists only.** An unchanged
  specialist does not raise its own objection to the new report; the reassigned
  specialist checks its report against the unchanged ones instead.
- **Short tasks.** Specialists get less direction from the plan and rely on
  their role definitions. Review still sends back reports that miss the task.
- **Single-specialist skip.** A lone report gets no cross-check, but there is
  nothing to cross-check it against.

## Faster responses (Step 12)

The optimisations above cut calls; these cut the time each request takes.

- **Concurrent review and critique calls.** A round's review calls, and the
  specialists' critique calls, are independent, so they now run at the same
  time instead of one after another. The calls and tokens are unchanged.
- **One reused model client.** The chat model is built once, so every call
  shares one connection pool instead of opening a new connection.
- **Shorter reports and strategy.** The roles asked for "a few short, concrete
  points", but reports ran 650–1,840 words (median 1,190) and strategies
  1,340–2,070. Each role now asks for at most 250 words and the strategy for at
  most 500. The model treats these as targets: reports came out at about 450
  words and strategies about 570. Shorter reports also shrink every prompt that
  carries them (review, critique, synthesis). Review is told to judge substance,
  not length, so shorter reports are not sent back for it; rejections did not
  rise.

Measured as above, on 2026-10-16, two runs of each scenario. "Before" is the
optimised version in the previous table.

| Scenario | Request | LLM calls | Tokens | Seconds |
| --- | --- | --- | --- | --- |
| gtm_risk | first | 21 → 15.5 | 72.5k → 24.8k (−66%) | 108 → 44 (−59%) |
| healthcare_scheduling | first | 19 → 20 | 74.2k → 37.1k (−50%) | 116 → 53 (−54%) |
| healthcare_scheduling | follow-up | 11 → 13.5 | 49.0k → 28.8k (−41%) | 86 → 48 (−44%) |
| premium_on_a_budget | first | 20 → 21.5 | 73.0k → 45.9k (−37%) | 109 → 64 (−41%) |
| premium_on_a_budget | follow-up | 11 → 11 | 47.9k → 26.3k (−45%) | 82 → 47 (−42%) |

The call counts move with the model's choices (how many reports are rejected,
how many conflicts are raised), not with these changes. In both `gtm_risk` runs
the planner assigned three specialists instead of four, so that row overstates
the gain; the other scenarios assigned the same specialists before and after.

Trade-offs:

- **Less detail per report.** Reports keep their recommendations and numbers
  but drop the longer explanations. The caps are constants (`REPORT_WORDS` in
  `agents/roles.py`, `STRATEGY_WORDS` in `agents/chief_of_staff.py`).
- **Bursts of calls.** Up to four calls run at once, so a low provider rate limit
  is reached sooner.

## Known gaps

- **Two runs per version.** Model output varies between runs (how many reports
  are rejected, how many conflicts are raised), so treat the percentages as
  approximate.

Fixed since the first measurements: the `tokens` metric now includes the
structured calls (plan, review, critique, resolve), which it used to leave out,
and the calls inside a node no longer run one after another. The token columns
above come from a LangChain callback, so they were complete all along.

## Sharper prompts and the Chief of Staff's reasoning (Step 16)

Step 16 rewrote every prompt and gave the Chief of Staff its own reasoning effort
(`AZURE_OPENAI_CHIEF_REASONING_EFFORT`); the specialists keep theirs
(`AZURE_OPENAI_REASONING_EFFORT`, `minimal`). This buys better decisions with
time, so it was measured before choosing the effort. Three scenarios at the same
time, against Azure OpenAI `gpt-5-mini` on 2026-10-16:

| Version | First request | Follow-up |
| --- | --- | --- |
| Before Step 16 (old prompts, everything at `minimal`) | 50–56 s | 45–62 s |
| New prompts, Chief of Staff at `medium` (chosen) | 89–130 s | 113–149 s |
| New prompts, Chief of Staff at `high` | 299–573 s | 197–224 s |

At `high` the Chief of Staff's stages dominate, because each waits for the one
before: planning 30–37 s, review 59–70 s, synthesis 42–59 s and resolving
conflicts 98–388 s. `medium` keeps them at 11–40 s each. The slowest resolves were
requests Azure stalled: no reply until the call timed out, then an identical retry
answered in under 90 s. The same happened once to a detailed strategy at `medium`
(a 300 s stall, then 29 s), so `LLM_TIMEOUT` now defaults to 120 s, a few times
the slowest normal call, to recover from a stall sooner.

Reports run longer with the new prompts, which ask for the arithmetic and
assumptions behind each figure: a median of about 660 words against about 520
before, still well over the 250 words asked for. Specialist calls barely slowed
(a median of 20 s against 18 s).

What the effort setting does on `gpt-5-mini`, measured on one pricing question
(two runs each):

| Effort | Reasoning tokens | Seconds |
| --- | --- | --- |
| `minimal` | 0 | 3.5–4.1 |
| `low` | 256–448 | 5.1–6.4 |
| `medium` | 640–960 | 7.8–10.8 |
| `high` | 3,136–3,648 | 25.4–28.8 |
| `xhigh` | 0 | 3.0–3.9 |

The API accepts `xhigh`, but the model then does no reasoning at all, so `high` is
the real maximum for this model.

What changed in the output, comparing the same scenario before and after:

- The objective names the decision the founder faces ("Decide whether to build
  and launch… and if yes…") instead of restating the request.
- Review uses a rubric and catches weak reports: in the healthcare scenario two
  of four first reports scored 3 (figures that did not reconcile) and came back
  at 4. The first version of the rubric rejected all eight reports across both
  rounds, including some it scored 4, and asked for things a 250-word brief
  cannot hold; it was calibrated, and the verdict now follows the score.
- Conflict decisions are concrete and agree with each other (a price, a number
  of clinics, a deferred feature) instead of hedged "hybrid paths".
- The strategy leads with go, go with conditions, or not yet, and its arithmetic
  ties together (budget, price, break-even, customers needed).

Trade-off: an evaluation takes about twice as long as before (and more calls when
review sends reports back), for better-founded decisions. Set
`AZURE_OPENAI_CHIEF_REASONING_EFFORT` to `minimal` to get the old speed with the
new prompts, or to `high` for the deepest reasoning at 5–10 minutes.

## The investment proposal and the reasoning sliders (Step 17)

The proposal is written on demand, so it adds nothing to an evaluation. Measured
against Azure OpenAI `gpt-5-mini` on 2026-10-16 and 17, with the default efforts
(specialists `minimal`, Chief of Staff `medium`), from the healthcare and premium
scenarios' team reports:

| Request | LLM calls | Tokens | Seconds |
| --- | --- | --- | --- |
| Write the proposal | 5, or 6 when Finance corrects its figures | 53k–60k | 57–82 |
| Write it, specialists at `low` | 5–6 | | 93 |
| Revise the market part (then Finance and the executive summary) | 3 | 41k–45k | 46–54 |
| Revise the risk part (then the executive summary), from the browser | 2 | | 40–43 |

The first write took 196 s: all three first-wave calls stalled until the 120 s
timeout and their retries answered in 15–30 s, the stall described above. A
proposal's calls write far more tokens than a report's (about 60k for the five),
because each part is structured data with prose fields.

What the live runs changed in the design, each fixed and tested:

- **Revenue and OpEx are calculated, not written.** At `minimal` reasoning, Finance
  wrote yearly OpEx that ignored its own monthly costs and the cost to serve
  customers (one run had 600 customers in year three on $96k of OpEx). Finance now
  gives the drivers of each year (customers, fixed costs, one-off fees) and the
  code works out revenue and OpEx from them, as it does NPV and IRR.
- **Finance is given what the other parts commit to.** Its first plans budgeted
  $400 a month for marketing against $1,200 of channels in the market part. It
  now receives the summed channel budgets, the staffing and the roadmap length.
- **Figures are checked, and Finance corrects them once.** The code checks
  year one's fixed costs against the launch OpEx, year three's revenue against
  the SOM, and each year's average customers against its year-end count. A failed
  check sends the plan back to Finance once; anything still failing is shown to
  the founder in the PDF and on the page, and the Chief of Staff is told.
- **The executive summary has to face weak returns.** Asked in the prompt, the
  Chief of Staff recommended going ahead without mentioning a negative NPV in four
  of seven runs, even when the prompt carried an explicit note. A required
  `financial_case` field ("what the investment metrics say and what follows from
  them") made it state the NPV and payback plainly, and argue for the pilot as a
  cheap test, in the runs since.
- **The content filter.** Azure's filter withheld Finance's reply twice in a row in
  one run, then not again in the seven runs since. A filtered structured reply is
  now retried once, like an unparseable one, and the filtered categories are
  logged, so a repeat says which filter fired.

Reasoning per request: `/evaluate` and the proposal requests take `reasoning`,
which the UI's sliders send. With the specialists at `low`, the proposal's
figures were more consistent (year one's OpEx matched twelve months of its own
costs, which `minimal` missed before the drivers were calculated in code) for
about a third more time.
