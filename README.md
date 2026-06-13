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

## Layout

The library is a `src`-layout package; only the deployable consumer and runtime artifacts
live outside it:

```text
src/ds_agent_loop/   # the publishable library (prompts, llm, data_gen, train, history, main)
entrypoint/          # a deployable consumer: run.py + config.py (pydantic-settings)
tests/               # pytest units against the installed package
state/ outputs/      # runtime artifacts (gitignored)
entrypoint/runs/     # per-run output dirs (gitignored)
```

## Run

The library installs a console script (`ds-agent-loop`):

```bash
uv run ds-agent-loop                                 # full toy run (N=10, patience=3)
uv run ds-agent-loop --iterations 5 --target-size 800
uv run python -m ds_agent_loop.main --iterations 5   # equivalent module form
```

Or run the bundled entrypoint, which writes results to a timestamped run directory:

```bash
uv run python entrypoint/run.py                       # -> entrypoint/runs/run_<dt>/results.text
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
