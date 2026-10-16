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

## Known gaps

- **Token counts in the response are low.** Structured calls (plan, review,
  critique, resolve) go through `with_structured_output`, which does not pass on
  the provider's usage, so the `tokens` metric covers only the specialist and
  synthesis calls: about 40–50% of the real total in these runs. Calls and
  seconds are complete. Requesting the raw reply (`include_raw=True`) would fix
  it.
- **Calls inside a node run one after another.** Review and critique loop over
  the reports sequentially; running those calls concurrently would cut latency
  further without changing the number of calls.
- **Two runs per version.** Model output varies between runs (how many reports
  are rejected, how many conflicts are raised), so treat the percentages as
  approximate.
