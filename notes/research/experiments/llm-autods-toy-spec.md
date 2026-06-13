# LLM Autonomous Data Scientist Toy Repo Spec

## Goal

Build a small Python repo where an LLM:
- generates a small seed delivery dataset,
- produces a simple reusable data-generation spec,
- reviews model results,
- proposes the next experiment step.

Python then:
- expands the dataset without more LLM calls,
- trains and evaluates scikit-learn models,
- records experiment history,
- repeats for `N` iterations.

This matches standard scikit-learn model-selection and evaluation workflows and uses structured JSON outputs from the LLM instead of fragile free-form parsing.[cite:30][cite:32][cite:17][cite:40]

## Scope

This is a toy offline experiment, not a production system. The repo should prefer readability and short files over abstractions, agents frameworks, or heavy orchestration code.[cite:30][cite:17]

Keep the task simple:
- Predict `delivery_time_minutes`.
- Start with a few features like `item_count`, `distance_km`, `traffic_level`, `is_raining`, `hour_of_day`.
- Compare a handful of regressors, not dozens.[cite:30][cite:35]

## Repo layout

```text
llm-autods-toy/
├── README.md
├── requirements.txt
├── .env.example
├── main.py
├── llm.py
├── data_gen.py
├── train.py
├── history.py
├── prompts.py
├── state/
│   ├── data_spec.json
│   ├── seed_rows.json
│   ├── dataset.csv
│   ├── history.json
│   └── best_run.json
└── outputs/
    └── run_summary.txt
```

This layout is intentionally flat so the project stays hackable. The state files make the experiment inspectable and easy to rerun from intermediate checkpoints.[cite:17][cite:30]

## Components

### `llm.py`

Small wrapper around the LLM API. It should only do two things: request seed dataset/spec generation, and request the next experiment proposal using structured JSON output. Structured Outputs are specifically meant to enforce a developer-supplied JSON schema, which is a good fit here.[cite:17][cite:40]

### `data_gen.py`

Owns dataset creation and expansion. It takes the saved `data_spec.json` and generates more synthetic rows locally so token usage does not grow with dataset size.[cite:17]

### `train.py`

Owns feature prep, model training, and scoring. Use a small model registry such as:
- `LinearRegression`
- `RandomForestRegressor`
- `GradientBoostingRegressor`
- optionally `HistGradientBoostingRegressor`

Use `cross_validate` or a simple train/test split for scoring; scikit-learn documents both as normal evaluation tools.[cite:32][cite:38]

### `history.py`

Append each run to `state/history.json`. Store:
- iteration number,
- dataset size,
- model type,
- hyperparameters,
- metrics,
- LLM rationale,
- timestamp.[cite:38]

### `main.py`

Runs the loop:
1. Create seed data/spec if missing.
2. Expand dataset.
3. Train/evaluate candidate model.
4. Ask LLM for next step.
5. Save history.
6. Repeat until `N` iterations.[cite:30][cite:38][cite:17]

## LLM contracts

Use two JSON schemas only.

### Seed generation schema

```json
{
  "seed_rows": [],
  "data_spec": {
    "features": [],
    "target": "delivery_time_minutes",
    "rules": [],
    "categories": {},
    "noise_level": 0.0
  }
}
```

The idea is: the LLM gives a small realistic sample plus a compact rule set that Python can reuse for cheap expansion. JSON-schema-constrained output is the right mechanism here because it reduces parser brittleness.[cite:17][cite:40]

### Next-step schema

```json
{
  "action": "keep_model | tune_hyperparameters | switch_model | expand_dataset | stop",
  "model_name": "",
  "hyperparameters": {},
  "reason": "",
  "notes": []
}
```

This keeps the LLM’s role narrow and interpretable. It is reasoning over results, not directly executing arbitrary code.[cite:17][cite:40]

## Training loop rules

Keep the loop intentionally dumb and small:
- Start with one baseline model.
- On each iteration, evaluate one proposed change.
- Accept the new run if the main metric improves.
- Save the best run separately.
- Stop after fixed iterations or no improvement for `k` rounds.[cite:30][cite:32]

Recommended primary metric:
- RMSE for easy interpretation.

Optional secondary metrics:
- `R^2`
- MAE.[cite:32][cite:38]

## Constraints

To avoid the repo turning into an uncontrolled agent sandbox:
- LLM may choose only from an allowlist of sklearn regressors.
- LLM may suggest only JSON config, not raw Python code execution.
- Python validates all hyperparameters before training.
- Dataset expansion always comes from the original saved spec, not from recursively regenerated specs each round.

Research on synthetic-data recursion warns that repeated self-generated loops can reduce diversity and distort distributions, so anchoring generation to a fixed seed spec is the safer toy design.[cite:31][cite:33][cite:42]

## Success criteria

The experiment is successful if it can:
- bootstrap a seed dataset from the LLM,
- grow the dataset locally,
- run multiple scikit-learn experiments,
- log decisions and scores to JSON,
- and show that the LLM can pick sensible next experiments from prior metrics.[cite:30][cite:32][cite:17]

## Non-goals

Do not add:
- multi-agent frameworks,
- background workers,
- databases,
- UI,
- prompt versioning systems,
- code execution from arbitrary LLM-generated Python,
- production-grade observability, auth, or retries.

This should stay a small personal experiment repo, not an MLOps project.[cite:30][cite:17]
