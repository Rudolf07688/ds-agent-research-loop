# A/B/C Memory Compaction Experiment Protocol

This protocol tests whether giving an LLM data-scientist agent too much raw experiment history eventually harms its decision quality, and whether periodic structured memory compaction improves future experimental performance by preserving high-level signal while removing low-value detail.[web:76][web:111][web:113]

## Research question

**Primary question:** Does unbounded inclusion of prior experiment history in an LLM data-scientist agent reduce future experiment quality after a threshold, and can periodic structured compaction outperform both full raw history and short recent history under a fixed experiment budget?[web:76][web:111][web:113]

**Hypotheses:**
- **H1:** Agent performance declines when all prior experiments are injected as raw context beyond a threshold.[web:76][web:113]
- **H2:** A compacted-memory strategy outperforms full raw history under the same budget.[web:111][web:112]
- **H3:** Compacted memory plus a short recent tail outperforms recent-only memory because it preserves long-range lessons without full-context noise.[web:111][web:112]

## Conditions

Use three experimental conditions:

| Condition | Memory visible to agent | Purpose |
|---|---|---|
| A: Recent-only | Last `k` raw experiment records only | Tests short working memory baseline |
| B: All-raw | All prior raw experiment records | Tests context overload hypothesis |
| C: Compacted+recent | Latest compaction artifact + last `k` raw records | Tests whether abstraction improves search |

All other components must remain fixed: same LLM, same prompt template, same model registry, same evaluation metric, same dataset, same random-seed policy, and same experiment budget. That isolation is necessary because ablation studies are only meaningful when one factor changes at a time.[web:103][web:111]

## Task setup

Use a controlled tabular ML setting:
- 5–10 tabular datasets, each either regression or classification.
- Same feature schema and train/validation/test split across all conditions.
- Same candidate model registry, for example: linear/logistic baseline, random forest, gradient boosting, histogram gradient boosting, XGBoost or LightGBM if allowed.
- Same allowed actions: switch model, tune hyperparameters, transform target, add/remove simple engineered features, expand dataset if synthetic generation is part of the setup.

To keep the experiment academically clean, fix one primary metric per dataset before the run starts, such as RMSE for regression or macro-F1 for classification.[web:113]

## Agent interface

At each iteration, the agent receives:
- dataset summary,
- current best run,
- allowed actions,
- memory context according to A/B/C condition,
- a strict output schema for the next proposed experiment.

The agent outputs:
- proposed action,
- model family,
- hyperparameters,
- reasoning,
- expected improvement mechanism.

Use the same structured schema across all conditions so memory strategy is the only manipulated variable. Structured and reflective memory papers consistently separate memory content from downstream decision format, which is exactly what you want here.[web:111]

## Memory representations

### Condition A: Recent-only
Provide only the last `k` experiments, for example `k = 5`.

### Condition B: All-raw
Provide all prior experiments in raw structured form.

### Condition C: Compacted+recent
Provide:
- one compacted memory artifact summarizing historical findings,
- plus the last `k` raw experiments.

The compaction artifact should be structured, not prose-only. Suggested fields:
- confirmed findings,
- failed directions,
- promising directions,
- best-known configs,
- unresolved questions,
- next-step recommendation,
- confidence,
- rationale.

This design follows the general principle in recent memory-management work that memory should be extracted, updated, and reused in a structured way rather than merely appended forever.[web:111]

## Compaction trigger

Define compaction before the experiment starts. Good options:
- every `m` experiments, for example every 10 runs,
- or when estimated memory tokens exceed threshold `t`.

For the main experiment, prefer a fixed compaction cadence such as every 10 runs because it is easier to compare statistically. A second experiment can test token-threshold triggering.[web:76][web:113]

## Step-by-step protocol

1. **Select datasets.** Choose 5–10 tabular tasks with moderate size and clear metrics. Record metadata for each dataset.
2. **Freeze splits.** Create one fixed train/validation/test split per dataset and reuse it for every condition.
3. **Freeze the agent action space.** Define the exact model families, hyperparameter ranges, and feature operations allowed.
4. **Freeze prompts.** Use one prompt template for experiment proposal and one for compaction. Do not modify prompts during the benchmark.
5. **Define budgets.** Example: 30 experiment iterations per dataset per condition, with 3 random seeds each.
6. **Initialize baseline memory.** All conditions start with the same dataset summary and no prior experiments.
7. **Run Condition A.** For each iteration, show only the last `k` raw runs; execute the proposed experiment; log outputs.
8. **Run Condition B.** Same process, but include all raw prior runs each time.
9. **Run Condition C.** Same process, but every `m` iterations generate a compaction artifact and thereafter provide that artifact plus the last `k` raw runs.
10. **Log everything.** For every iteration store prompt, visible memory IDs, token count, chosen action, metrics, runtime, and whether the run improved on the incumbent.
11. **Repeat across seeds.** Run each dataset-condition pair with multiple seeds to reduce variance from stochasticity in both model training and LLM proposals.
12. **Analyze outcomes.** Compare conditions on predefined metrics and run significance tests.

This protocol gives a full factorial comparison over datasets and memory strategies while keeping the intervention narrow and auditable.[web:103][web:111]

## Compaction sub-protocol

At compaction time:
1. Retrieve the designated source experiments.
2. Ask the LLM to extract durable findings, failed directions, and promising next directions.
3. Save the artifact to the database with source lineage.
4. Do not allow the compactor to see future outcomes.
5. Use the resulting artifact unchanged until the next compaction point.

That prevents leakage and makes the compaction step a legitimate causal variable rather than an ad hoc summary rewritten after the fact.

## Outcome measures

### Primary outcome
- **Best achieved test-set score under fixed experiment budget.**

### Secondary outcomes
- Best validation score by iteration.
- Area under improvement curve across iterations.
- Number of improving steps.
- Time or iterations to reach 90% of final best score.
- Repetition rate, defined as semantically similar experiments repeated after failure.
- Search diversity, measured by number of distinct model families or transformation types tried.
- Prompt token count per decision.

This combination matters because memory strategies may improve not only final score but also search efficiency and exploration quality.[web:112][web:113]

## Statistical analysis

Use dataset-level paired comparisons because each dataset is evaluated under all three conditions.

Recommended:
- Per-dataset paired difference plots.
- Wilcoxon signed-rank test or paired t-test, depending on sample properties.
- Bootstrap confidence intervals for effect sizes.
- Mixed-effects regression if you want a cleaner publication-level analysis, with dataset as random effect and memory strategy as fixed effect.

Main comparisons:
- A vs B to test overload harm.
- B vs C to test compaction benefit.
- A vs C to test whether compaction beats simple recency.

## Failure analysis

Pre-register a manual error taxonomy for a sample of runs:
- repeated failed idea,
- overfitting-focused proposal,
- irrelevant model switch,
- metric misunderstanding,
- forgetting earlier lesson,
- contradiction with known findings.

Then annotate a subset of trajectories. If B produces more contradictions and repeated failed ideas than C, that becomes strong qualitative evidence for your mechanism claim, not just a score difference.

## Documentation requirements

For academic reporting, each run should record:
- dataset ID,
- condition,
- seed,
- iteration number,
- memory artifacts shown,
- prompt version,
- proposal JSON,
- actual executed config,
- validation metrics,
- test metrics,
- compaction artifact if applicable,
- token usage.

That level of traceability is important because the claim is about **memory design as a causal factor**, not merely about performance.

## Paper-style structure

A clean write-up could be:
- **Introduction:** memory overload problem in agentic experimentation.[web:76][web:113]
- **Hypothesis:** raw history eventually harms performance; compaction restores signal.[web:111]
- **Method:** A/B/C memory ablation with fixed budgets and controlled action space.
- **Results:** primary and secondary metrics across datasets.
- **Analysis:** threshold effects, token-growth curves, and failure taxonomy.
- **Discussion:** implications for agent memory systems and autonomous ML search.

## Strongest version of the experiment

If you want the strongest publication-style result, add one more analysis:
- vary the history length `k` and compaction interval `m`.

That lets you produce a threshold curve rather than just a single A/B/C result. Then the contribution becomes: **there exists a measurable context-size threshold beyond which raw memory hurts, and structured compaction shifts that threshold or avoids the decline.**[web:76][web:113][web:116]
