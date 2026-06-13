# Phase 1 Data Model: LLM Autonomous Data Scientist (Toy) Loop

All entities are persisted as human-readable files under `state/` (plus a summary under
`outputs/`). Field names below are the canonical on-disk keys. Per Constitution Principle
VIII, these structured entities are realized as Pydantic models (used to validate the
LLM's structured outputs), and `RunConfig` is a centralized `pydantic-settings` Settings
object loaded from `.env` / environment / CLI.

## DeliveryRecord

A single synthetic delivery observation (a row of the dataset).

| Field                   | Type    | Notes                                              |
|-------------------------|---------|----------------------------------------------------|
| `item_count`            | int     | ≥ 1                                                |
| `distance_km`           | float   | ≥ 0                                                |
| `traffic_level`         | string  | categorical (e.g. `low`/`medium`/`high`)           |
| `is_raining`            | bool    | rain indicator                                     |
| `hour_of_day`          | int     | 0–23                                               |
| `delivery_time_minutes` | float   | target; ≥ 0                                        |

- Seed rows are stored in `state/seed_rows.json`; the full working set (seed + expanded)
  is stored in `state/dataset.csv`.
- Validation: every row produced by expansion MUST satisfy the ranges/categories defined
  in the DataSpec.

## DataSpec  (`state/data_spec.json`)

LLM-authored, reusable description that anchors all local expansion. Written once, never
regenerated mid-run.

| Field         | Type            | Notes                                                  |
|---------------|-----------------|--------------------------------------------------------|
| `features`    | array<string>   | feature names (the non-target columns)                 |
| `target`      | string          | fixed: `delivery_time_minutes`                         |
| `rules`       | array<string>   | human-readable generation rules Python applies          |
| `categories`  | object          | map feature → allowed category values                   |
| `noise_level` | number          | ≥ 0; controls additive noise on the target              |

- Relationships: drives generation of every DeliveryRecord during expansion.
- Invariant (Principle V): once saved, treated as immutable for the rest of the run.

## Dataset  (`state/dataset.csv`)

The working collection of DeliveryRecords (seed + locally expanded). Has a `size` (row
count) used in history and stop logic. Grows by local expansion only.

## RunRecord  (entry in `state/history.json`)

One iteration's outcome. `history.json` is an append-only array of these.

| Field             | Type            | Notes                                              |
|-------------------|-----------------|----------------------------------------------------|
| `iteration`       | int             | 1-based iteration index                            |
| `dataset_size`    | int             | row count used for this run                        |
| `model_name`      | string          | MUST be in the allowlist                           |
| `hyperparameters` | object          | validated config actually used                     |
| `metrics`         | object          | `{ "rmse": float, "r2"?: float, "mae"?: float }`   |
| `rationale`       | string          | LLM's reason for the step that led to this run     |
| `timestamp`       | string (ISO)    | when the run completed                             |

- Validation: `model_name` ∈ allowlist; `metrics.rmse` present; `hyperparameters` are
  the validated set.

## BestRun  (`state/best_run.json`)

The single best result so far — same shape as a RunRecord. Updated only when a run's
primary metric (`rmse`, lower is better) improves on the stored best.

## NextStepDecision  (transient; the LLM's structured next-step output)

Constrained proposal for the next iteration. Validated before use; never executed as
code.

| Field             | Type            | Notes                                                       |
|-------------------|-----------------|-------------------------------------------------------------|
| `action`          | enum            | one of `keep_model`, `tune_hyperparameters`, `switch_model`, `expand_dataset`, `stop` |
| `model_name`      | string          | required for `switch_model`/`keep_model`; MUST be in allowlist |
| `hyperparameters` | object          | validated before training                                   |
| `reason`          | string          | rationale                                                   |
| `notes`           | array<string>   | optional free-form notes                                    |

- Validation (Principle III): reject if `action` outside enum, `model_name` outside
  allowlist, hyperparameters invalid, or any non-conforming content is present.

## ModelAllowlist  (code constant in `train.py`)

Fixed set of approved regressors the LLM may choose from:
`LinearRegression`, `RandomForestRegressor`, `GradientBoostingRegressor`,
`HistGradientBoostingRegressor` (optional). Anything outside is rejected.

## RunConfig  (centralized `pydantic-settings` Settings object)

Single source of truth for runtime configuration; loaded from `.env` / environment, with
CLI overrides. Also carries LLM credentials/model name.

| Field            | Type | Default | Notes                                   |
|------------------|------|---------|-----------------------------------------|
| `n_iterations`   | int  | 10      | total loop iterations (`N`)             |
| `patience`       | int  | 3       | stop after `k` rounds w/o improvement   |
| `target_size`    | int  | (spec)  | dataset row target for expansion        |
| `primary_metric` | enum | `rmse`  | metric used for acceptance              |
| `llm_model`      | str  | (.env)  | LLM model name                          |
| `llm_api_key`    | str  | (.env)  | LLM API key (never committed)           |

## Entity Relationships

- **DataSpec** → generates → **DeliveryRecord**s → comprise → **Dataset**.
- Each loop iteration: **Dataset** + **NextStepDecision** → train/score → **RunRecord**
  → appended to history; may update **BestRun**.
- **NextStepDecision** is produced by the LLM from prior **RunRecord**s and constrained
  by **ModelAllowlist**.
