# LLM Autonomous Data Scientist (Toy) Loop

A small offline experiment: an LLM bootstraps a seed delivery dataset plus a reusable
generation spec (one structured-JSON call) and proposes the next experiment step
(structured-JSON call) by reasoning over recorded metrics. Python owns everything else —
local dataset expansion from the fixed spec, training/scoring one scikit-learn regressor
per iteration, recording history, tracking the best run, and looping with an early stop.

Safety is enforced in Python: a model allowlist, hyperparameter validation, and
JSON-config-only LLM authority (no code execution).

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management and running scripts
- An API key for an OpenAI-compatible provider that supports JSON-schema structured output

## Setup

```bash
uv sync                  # resolve & install deps from pyproject.toml / uv.lock
cp .env.example .env     # then edit .env with your API key + model name
```

## Run

```bash
uv run python main.py                                  # full toy run (N=10, patience=3)
uv run python main.py --iterations 5 --target-size 800
```

The first run makes one LLM seed-generation call and saves `state/seed_rows.json` +
`state/data_spec.json`. Subsequent runs reuse them (no seed call) and resume from saved
state.

## Inspect results

```bash
cat state/best_run.json        # best model/score so far
cat state/history.json         # every iteration: model, params, metrics, rationale
cat outputs/run_summary.txt    # human-readable summary
```

## Test

```bash
uv run pytest    # pure-Python units: expansion, validation, history, stop conditions
```
