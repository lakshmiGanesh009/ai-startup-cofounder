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
