# Phase 0 Research: LLM Autonomous Data Scientist (Toy) Loop

The source notes and the project constitution resolve most decisions. This document
records the deliberate choices, their rationale, and the alternatives rejected. There
are no remaining NEEDS CLARIFICATION items.

## Decision 1: LLM output via JSON-schema-constrained structured outputs

- **Decision**: Use the LLM provider's structured-output / JSON-schema mode for both
  calls. The two schemas live in `prompts.py` and are validated on receipt.
- **Rationale**: Constitution Principle II mandates structured JSON only and forbids
  free-form parsing. Schema-constrained output removes parser brittleness and keeps the
  LLM's role narrow.
- **Alternatives rejected**: Free-form text + regex/JSON extraction (brittle, violates
  Principle II); function-calling with many tools (over-engineered for two fixed jobs).

## Decision 2: Local dataset expansion anchored to a fixed saved spec

- **Decision**: `data_gen.py` reads the saved `state/data_spec.json` once and generates
  additional rows in pure Python (numpy-driven sampling per the spec's features, rules,
  categories, and noise level). The spec is never regenerated mid-run.
- **Rationale**: Constitution Principle V + spec FR-004/FR-005. Keeps token cost
  independent of dataset size and avoids synthetic-data recursion that degrades
  diversity/distribution.
- **Alternatives rejected**: Asking the LLM to emit each batch of rows (cost scales with
  size, recursion risk); regenerating the spec per iteration (distribution drift).

## Decision 3: Small fixed model allowlist + Python-side validation

- **Decision**: A registry/allowlist of scikit-learn regressors:
  `LinearRegression`, `RandomForestRegressor`, `GradientBoostingRegressor`, and
  optionally `HistGradientBoostingRegressor`. `train.py` maps an allowlisted name +
  validated hyperparameters to an estimator; anything outside the allowlist or any
  invalid hyperparameter is rejected before training.
- **Rationale**: Constitution Principle III + spec FR-007/FR-008/FR-009. The LLM reasons
  over results but never executes code; Python is the sole authority on what runs.
- **Alternatives rejected**: Letting the LLM name arbitrary estimators or pass arbitrary
  kwargs (unsafe, unbounded); `eval`-ing LLM-supplied code (explicitly prohibited).

## Decision 4: Evaluation metric and method

- **Decision**: Primary metric RMSE (interpretable, same units as the target). Optional
  secondary metrics R² and MAE. Scoring via a simple train/test split or
  `cross_validate`; start with one and keep it consistent across runs for comparability.
- **Rationale**: Spec success criteria + constitution Scope constraints. RMSE is easy to
  interpret; scikit-learn documents both split and CV as normal evaluation tools.
- **Alternatives rejected**: Classification metrics (wrong task); elaborate nested CV /
  hyperparameter search (out of scope for a toy).

## Decision 5: Loop control and acceptance

- **Decision**: One candidate change evaluated per iteration. Accept a run as the new
  best only when its primary metric (RMSE, lower is better) improves on the saved best.
  Stop after `N` iterations or after `k` consecutive rounds without improvement. `N` and
  `k` are configurable with small defaults (e.g. `N=10`, `k=3`).
- **Rationale**: Spec FR-013/FR-014 + Story 5; constitution "intentionally dumb and
  small" loop.
- **Alternatives rejected**: Multi-candidate parallel evaluation per round (complexity);
  unbounded loops (no termination guarantee).

## Decision 6: State persistence and checkpoint resume

- **Decision**: All durable state is human-readable files under `state/`. On start,
  reuse existing valid `seed_rows.json` + `data_spec.json` instead of recalling the LLM;
  append each run to `history.json`; keep `best_run.json` separate; write a
  human-readable `outputs/run_summary.txt`.
- **Rationale**: Constitution Principle IV + spec FR-003/FR-011/FR-012/FR-015/FR-017 and
  SC-006/SC-007.
- **Alternatives rejected**: A database or binary formats (violates inspectability and
  the non-goals); regenerating seed data every run (wasteful, non-resumable).

## Decision 7: Configuration and credentials

- **Decision**: LLM credentials/model name read from a local `.env` (documented via
  `.env.example`), loaded with python-dotenv. Run parameters (`N`, `k`, target dataset
  size, metric) are simple CLI args / module constants with sensible defaults.
- **Rationale**: Constitution Scope constraints; secrets stay local and uncommitted.
- **Alternatives rejected**: A config framework / settings service (over-engineered for
  a toy); committing keys (insecure).

## Decision 8: Testing approach

- **Decision**: pytest units cover the pure-Python logic that does not need an LLM:
  expansion-from-spec (no LLM call, anchored to saved spec), model allowlist +
  hyperparameter validation/rejection, history append, best-run selection, and
  stop-condition logic. LLM calls are exercised manually, not in the automated loop.
- **Rationale**: Keeps tests deterministic, fast, and offline while still covering the
  safety-critical validation paths (Principle III) and the loop's correctness.
- **Alternatives rejected**: Mocking the full LLM round-trip in unit tests (low value
  for a toy, adds maintenance); no tests at all (validation paths are safety-relevant).
