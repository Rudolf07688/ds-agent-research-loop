# Directional Research Memory — Autonomous Data-Scientist Agent

## Quick Start

```bash
uv sync
gcloud auth application-default login
gcloud config set project research-se-gen-ai
uv run ds-agent-loop                        # full run (N=10, patience=3)
cat state/best_run.json                     # best model/score
cat state/history.json                      # full iteration log
```

Re-runs skip the seed call and resume from saved state. Add `--iterations 5 --target-size 800` etc. to override defaults.

---


A research codebase studying one question: **does an LLM data-scientist agent get *worse* the more
raw history you give it, and can a structured, compact "research memory" fix that?**

An LLM agent iteratively runs ML experiments (pick a model, tune it, expand the data, stop). The
thesis — *Directional Research Memory: Compaction as Momentum in Experiment Space* — is that beyond
some threshold, feeding the agent more **raw** episodic history hurts performance, while replacing
that history with a **structured compaction** of what's true / what failed / what's unresolved /
where to search next preserves the *direction* of learning (like optimization momentum) and improves
both sample efficiency and final results.

The codebase exists to make that claim **demonstrable or falsifiable with replayable evidence**: a
benchmark of tabular tasks, an A/B/C ablation over three memory regimes, and a fully logged,
reproducible experiment harness. See `notes/research/paths/001-directional-research-memory-thesis-story.md`
for the long-form story and `.specify/memory/constitution.md` for the governing principles.

> **Status (developer note).** What runs end-to-end **today** is the single-dataset agent loop
> (sections [Setup](#setup) → [Run](#run)). The **memory-regime ablation harness** — three regimes,
> the Directional Research Memory compaction operator, the multi-dataset benchmark, Postgres
> persistence, and the paired statistical analysis — is the **active build**, specified in
> `specs/003-memory-compaction-ablation/` (`plan.md`, `data-model.md`, `contracts/`). Commands for
> that harness are marked **(planned)** below.

## The three memory regimes (what the study compares)

Everything is held fixed except the slice of history the agent sees before each decision:

- **A — recent-only**: the last `k` raw experiment records.
- **B — all-raw**: every prior raw record (the regime expected to degrade).
- **C — compacted+recent**: one structured **Directional Research Memory** artifact + the last `k`
  raw records.

## Safety model (unchanged, non-negotiable)

The LLM only ever returns **structured JSON** that Python validates and acts on — never code it runs:

- A fixed, developer-owned **model allowlist** (regressors *and* classifiers); hyperparameters are
  validated before any estimator is built.
- Sanctioned LLM jobs only: seed-data generation, next-step proposal, and — for regime C —
  research-memory compaction. Each is hosted by a **minimal, tool-less Google ADK agent** with an
  `output_schema`.

Backend: **Google Gemini on Vertex AI** via the `google.genai` SDK. Auth is **Application Default
Credentials (ADC)** — no API keys, never committed or baked into images.

## Prerequisites

- Python 3.13 (pinned in `.python-version`)
- [uv](https://docs.astral.sh/uv/) for dependency management and running everything
- A Google Cloud project with the Vertex AI API enabled, and **ADC**
- Docker + Docker Compose (only for the containerized sweep with Postgres)

## Setup

```bash
uv sync                                  # resolve & install deps from pyproject.toml / uv.lock
gcloud auth application-default login    # ADC — authenticates the agent to Vertex AI
gcloud config set project research-se-gen-ai
cp .env.example .env                     # optional: override project/location/model/run params
```

Defaults (all overridable via environment / `.env`): project `research-se-gen-ai`, location
`global`, model `gemini-3.5-flash`. Only valid ADC credentials are mandatory.

## Layout

A `src`-layout package; only the deployable consumer and runtime artifacts live outside it:

```text
src/ds_agent_loop/   # the library
  prompts.py         #   typed models, settings, the sanctioned JSON schemas + prompts
  llm.py             #   thin Vertex/Gemini wrapper (one tool-less ADK agent per call)
  data_gen.py        #   local synthetic-data expansion from a fixed spec (no LLM)
  train.py           #   model allowlist, hyperparameter validation, training/scoring
  history.py         #   run/best-run state
  main.py            #   the experiment loop
  # planned (spec 003): benchmark.py, memory.py, compaction.py, store.py, experiment.py, analysis.py
entrypoint/          # deployable consumer: run.py + config.py + smoke_live.py
tests/               # pytest units against the package (hermetic, no network)
docker-compose.yml   # backend + Postgres (postgres:17-alpine)
state/ outputs/      # runtime artifacts (gitignored)
specs/ notes/        # specs (Spec Kit) and human-readable progress/research notes
```

## Run (single agent loop — works today)

The library installs a console script (`ds-agent-loop`):

```bash
uv run ds-agent-loop                                 # full run (N=10, patience=3)
uv run ds-agent-loop --iterations 5 --target-size 800
uv run python -m ds_agent_loop.main --iterations 5   # equivalent module form
```

Or the bundled entrypoint, which writes to a timestamped run directory:

```bash
uv run python entrypoint/run.py                      # -> entrypoint/runs/run_<dt>/results.text
```

The first run makes one LLM seed-generation call and saves `state/seed_rows.json` +
`state/data_spec.json`; later runs reuse them (no seed call) and resume from saved state.

### Inspect results

```bash
cat state/best_run.json        # best model/score so far
cat state/history.json         # every iteration: model, params, metrics, rationale
cat outputs/run_summary.txt    # human-readable summary
```

## Run the memory-regime ablation (planned — spec 003)

Once the harness lands, the research workflow is a single containerized command that brings up
Postgres, runs every `(dataset × regime × seed)` cell to its budget, and exits cleanly:

```bash
docker compose up --build                            # (planned) full A/B/C sweep -> Postgres

# single cell, for development / smoke:
uv run python -m ds_agent_loop.main \
  --dataset delivery_time --regime compacted_recent --seed 0 --k 5 --m 10 --iterations 30   # (planned)

# export everything to inspectable JSON/CSV, then analyze:
uv run python -m ds_agent_loop.store export --out outputs/export                              # (planned)
uv run python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis          # (planned)
```

The harness keeps every run **replayable and resumable** (interrupted sweeps don't recompute
finished cells), persists the **exact memory shown** before each decision, and emits **structured
logs to stdout and Postgres**. Full walkthrough: `specs/003-memory-compaction-ablation/quickstart.md`.

## Live verification (manual, real Vertex AI call)

The offline test suite is hermetic. To verify a real Gemini/Vertex round-trip (excluded from
`pytest`):

```bash
uv run python entrypoint/smoke_live.py            # one live run + success-criteria checks
uv run python entrypoint/smoke_live.py            # re-run: resumes (skips the seed call)
uv run python entrypoint/smoke_live.py --fresh    # clears smoke state to force a first run
```

## Container

Build a portable image (library + consumer); supply credentials at launch and persist artifacts via
mounts. **No secrets are baked in** — credentials are always mounted at run time.

```bash
./docker-build.sh                                  # runs gitleaks against .env before building
```

`docker compose up` (above) is the preferred path since it also brings up Postgres. For a standalone
container run:

```bash
docker run --rm \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc/key.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/adc/key.json:ro" \
  -v "$PWD/entrypoint/runs:/app/entrypoint/runs" \
  ds-agent-loop
```

Real env vars (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL`, …) override baked
defaults and `.env`. Mount `state/` (`-v "$PWD/state:/app/state"`) for a shared, resumable run.
Running without credentials fails fast.

## Test

```bash
uv run pytest    # hermetic units: data expansion, validation, history, stop conditions, and the
                 # tool-less ADK agent posture — makes no network/LLM calls
```

For a real LLM round-trip, use the manual live smoke script (see **Live verification**).

## Where to read more

| Topic | Path |
|-------|------|
| The thesis story / long-term direction | `notes/research/paths/001-directional-research-memory-thesis-story.md` |
| Governing principles (the constitution) | `.specify/memory/constitution.md` |
| Spec roadmap toward the thesis | `notes/000-spec-list.md` |
| Active build: memory-regime ablation | `specs/003-memory-compaction-ablation/` |
