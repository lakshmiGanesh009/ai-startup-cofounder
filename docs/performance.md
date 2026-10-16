# Performance

Every `/evaluate` response carries a `metrics` map: one entry per node, each with
the LLM `calls` it made, the wall-clock `seconds` it took, and `tokens` (summed
from the model's usage when the provider reports it). The totals below are the
sum across nodes for one run.

## How to measure

Run the Step 9 scenarios against a real model and read the `metrics` map:

```bash
uv run python demo.py scenarios/healthcare_scheduling.json
uv run python demo.py scenarios/gtm_risk.json
uv run python demo.py scenarios/premium_on_a_budget.json
```

Record total LLM calls and total seconds per run. Baseline is the workflow before
the optimisations below; "optimised" is after.

## What was optimised

- **Skip cross-critique for a single specialist.** When the plan assigns only one
  specialist, there is no one to cross-critique against, so the critique and
  resolve pass is skipped. This removes one critique call per assigned specialist
  and one resolve call per conflict on narrow requests.
- **Review and critique skip unavailable reports.** A specialist whose call failed
  produces a gap marker rather than a report; the review and critique nodes skip
  it instead of spending a call on nothing.
- **Single-revision cap** (`MAX_ITERATIONS`, `MAX_CRITIQUE_ROUNDS` = 1) bounds the
  review and critique loops, so a weak report costs at most one extra call.

## Baseline vs optimised

Fill from live runs. Numbers are totals for one request.

| Scenario | LLM calls (baseline) | LLM calls (optimised) | Seconds (baseline) | Seconds (optimised) |
| --- | --- | --- | --- | --- |
| healthcare_scheduling | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| gtm_risk | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| premium_on_a_budget | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Trade-off

Skipping cross-critique for a single specialist trades a small amount of coverage
(no cross-check on a lone report) for fewer calls and lower latency. A single
report has nothing to be cross-checked against, so the loss is negligible, while
multi-specialist requests keep the full critique pass.
