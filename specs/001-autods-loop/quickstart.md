# Quickstart: LLM Autonomous Data Scientist (Toy) Loop

A small offline experiment: an LLM bootstraps a seed dataset + reusable spec and picks
the next experiment step; Python expands data locally, trains/scores scikit-learn
regressors, and logs everything to inspectable JSON.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management and running scripts
- An LLM API key for a provider that supports structured/JSON-schema output

## Setup

```bash
uv sync                     # resolve & install deps from pyproject.toml / uv.lock
cp .env.example .env        # then edit .env with your API key + model name
```

## Run

```bash
uv run python main.py                          # full toy run (N=10, patience=3)
uv run python main.py --iterations 5 --target-size 800
```

First run makes one LLM seed-generation call and saves `state/seed_rows.json` +
`state/data_spec.json`. Subsequent runs reuse them (no seed call) and resume from saved
state.

## Inspect results

```bash
cat state/best_run.json        # best model/score so far
cat state/history.json         # every iteration: model, params, metrics, rationale
cat outputs/run_summary.txt    # human-readable summary
```

## What to verify (maps to success criteria)

- **SC-001**: empty workspace → `state/seed_rows.json` + `state/data_spec.json` appear.
- **SC-002**: increase `--target-size` → larger `dataset.csv`, no extra LLM seed call.
- **SC-003**: an `N`-iteration run → ≥ `N` entries in `history.json` + a `best_run.json`.
- **SC-004**: any out-of-allowlist model or invalid hyperparameters is rejected, not run.
- **SC-005**: best recorded RMSE never worse than the baseline model's.
- **SC-006/007**: stop and restart mid-experiment → resumes without re-seeding; the run
  is reconstructable from `state/` alone.

## Tests

```bash
uv run pytest   # pure-Python units: expansion, validation, history, stop conditions
```
