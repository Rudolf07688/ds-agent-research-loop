# LLM Autonomous Data Scientist (Toy) Loop

A small offline experiment: an LLM bootstraps a seed delivery dataset plus a reusable
generation spec (one structured-JSON call) and proposes the next experiment step
(structured-JSON call) by reasoning over recorded metrics. Python owns everything else —
local dataset expansion from the fixed spec, training/scoring one scikit-learn regressor
per iteration, recording history, tracking the best run, and looping with an early stop.

Safety is enforced in Python: a model allowlist, hyperparameter validation, and
JSON-config-only LLM authority (no code execution).

The LLM backend is **Google Gemini on Vertex AI**, accessed via the `google.genai` SDK and
hosted by a **minimal Google ADK agent** (one tool-less agent per call). The two structured
schemas, the model allowlist, and the bounded-agency rules are unchanged.

## Prerequisites

- Python 3.13 (pinned in `.python-version`)
- [uv](https://docs.astral.sh/uv/) for dependency management and running scripts
- A Google Cloud project with the Vertex AI API enabled, and **Application Default
  Credentials (ADC)** — no API key is used

## Setup

```bash
uv sync                                  # resolve & install deps from pyproject.toml / uv.lock
gcloud auth application-default login    # ADC — authenticates the loop to Vertex AI
gcloud config set project research-se-gen-ai
# Optional: copy .env.example -> .env only to override project/location/model defaults.
```

Defaults (all overridable via environment): project `research-se-gen-ai`, location `global`,
model `gemini-3.5-flash`. Only valid ADC credentials are mandatory. Credentials are never
committed or baked into images.

## Layout

The library is a `src`-layout package; only the deployable consumer and runtime artifacts
live outside it:

```text
src/ds_agent_loop/   # the publishable library (prompts, llm, data_gen, train, history, main)
entrypoint/          # a deployable consumer: run.py + config.py + smoke_live.py
tests/               # pytest units against the installed package (hermetic, no network)
Dockerfile           # multi-stage uv build; runs the consumer entrypoint
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

## Live verification (manual, real Vertex AI call)

The offline test suite is hermetic (no network). To verify a real Gemini/Vertex round-trip,
authenticate with ADC (above) and run the manual smoke script — it is deliberately excluded
from `pytest`:

```bash
uv run python entrypoint/smoke_live.py            # one live run + success-criteria checks
uv run python entrypoint/smoke_live.py            # re-run: resumes (skips the seed call)
uv run python entrypoint/smoke_live.py --fresh    # clears smoke state to force a first run
```

It asserts seed files are created, iterations complete, a results file is written, and the
best run is no worse than the baseline. It uses a persistent state dir so a second run
exercises the resume (zero-seed) path.

## Container

Build a portable image (library + consumer) and run it with credentials supplied at launch
and artifacts persisted via a mounted volume. **No secrets are baked in**, but a local
`.env` (if present at build time) *is* baked in to seed non-secret defaults — project,
location, model, run params — so the image runs with almost no setup. Credentials must never
live in `.env` (see `.env.example`); they are always mounted at run time.

```bash
# Preferred: runs gitleaks against .env before building to catch accidental secrets.
# Install gitleaks first: brew install gitleaks (or see https://github.com/gitleaks/gitleaks)
./docker-build.sh

# Minimal run: relies on baked-in defaults (and your local .env, if any). Only credentials
# need to be supplied.
docker run --rm \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc/key.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/adc/key.json:ro" \
  -v "$PWD/entrypoint/runs:/app/entrypoint/runs" \
  ds-agent-loop
```

To **override** any default, pass it as an environment variable — real env vars take
precedence over both the baked defaults and `.env`:

```bash
docker run --rm \
  -e GOOGLE_GENAI_USE_VERTEXAI=TRUE \
  -e GOOGLE_CLOUD_PROJECT=research-se-gen-ai \
  -e GOOGLE_CLOUD_LOCATION=global \
  -e GEMINI_MODEL=gemini-3.5-flash \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc/key.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/adc/key.json:ro" \
  -v "$PWD/entrypoint/runs:/app/entrypoint/runs" \
  ds-agent-loop
```

Mount `state/` as well (`-v "$PWD/state:/app/state"`) for a shared, resumable run; otherwise
each container run re-seeds in isolated state. Running without credentials fails fast.

## Inspect results

```bash
cat state/best_run.json        # best model/score so far
cat state/history.json         # every iteration: model, params, metrics, rationale
cat outputs/run_summary.txt    # human-readable summary
```

## Test

```bash
uv run pytest    # hermetic units: expansion, validation, history, stop conditions,
                 # and the tool-less ADK agent posture — makes no network/LLM calls
```

For a real LLM round-trip, use the manual live smoke script (see **Live verification**).
