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

## Run the memory-regime ablation (spec 003)

The research workflow is a single containerized command that brings up Postgres, runs every
`(dataset × regime × seed [× k × m])` cell to its budget, persists everything, and exits cleanly:

```bash
docker compose up --build                            # full A/B/C sweep -> Postgres
#   STUB_LLM=1 docker compose up                      # offline plumbing check (no Vertex calls)

# single cell, for development / smoke (regime ∈ recent_only | all_raw | compacted_recent):
uv run python -m ds_agent_loop.main \
  --dataset delivery_time --regime compacted_recent --seed 0 --k 5 --m 10 --iterations 30

# the full sweep on its own (resumes; completed cells are not recomputed):
uv run python -m ds_agent_loop.experiment sweep --seeds 0,1,2,3,4

# (US5) threshold sweep over the recent-window k and compaction cadence m:
uv run python -m ds_agent_loop.experiment sweep --grid-k 3,5,10 --grid-m 5,10,20

# export everything to inspectable JSON/CSV, then analyze:
uv run python -m ds_agent_loop.store export --out outputs/export
uv run python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis --threshold-curves
```

**What each regime shows the agent.** `recent_only` = the last `k` raw experiment records;
`all_raw` = every prior record (prompt tokens grow unboundedly — recorded as evidence for H1, and
a cell that exceeds the model context is stopped and marked `context_limited`, never silently
truncated); `compacted_recent` = one **Directional Research Memory** artifact (a schema-constrained
projection of the trajectory onto confirmed/failed/promising/unresolved beliefs, regenerated by a
third sanctioned LLM call every `m` experiments) **plus** the last `k` raw records.

The analysis emits the primary outcome (best test score under budget), the secondary trajectory
outcomes — including the **best-so-far regret curve** — and the per-dataset paired comparisons
A-vs-B / B-vs-C / A-vs-C (Wilcoxon + bootstrap CIs), improvement & token-growth plots, optional
`(k, m)` threshold curves, and an HTML note under `notes/`.

The harness keeps every run **replayable and resumable** (interrupted sweeps don't recompute
finished cells), persists the **exact memory shown** before each decision, and emits **structured
logs to stdout and Postgres**. Full walkthrough: `specs/003-memory-compaction-ablation/quickstart.md`.

## Materialize & export the versioned benchmark (spec 004)

The benchmark suite is a **fixed, versioned, Postgres-persisted** artifact: each member's fixed
factors (task type, primary metric + direction, frozen action space, model allowlist, budget,
patience) and its stratified, content-hashed train/val/test split are materialized into the
`benchmark_members` / `benchmark_splits` tables (Alembic migration `0002`; schema is created
**only** via `alembic upgrade head`, never an operational `create_all`).

```bash
uv run alembic upgrade head                                   # creates the two tables

# materialize the suite under BENCHMARK_VERSION (idempotent; re-run is a no-op unless data drifts):
uv run python -m ds_agent_loop.benchmark materialize          # or: --datasets diabetes,wine

# export a member to DB-free, byte-identical JSON/CSV (descriptor.json + rows.csv + split.json):
uv run python -m ds_agent_loop.benchmark export wine outputs/benchmark
```

Members load by id (`benchmark.load_member`) with a content-hash assertion guaranteeing
byte-identical reuse across processes; classification splits are stratified so every class appears
in every partition. Any change to a fixed factor without a `BENCHMARK_VERSION` bump is rejected
loudly (`BenchmarkDriftError`), and a new version coexists with the old so prior results stay
attributable. The loop (`main` / `experiment sweep`) resolves each member's descriptor + frozen
split from this materialized suite — no dataset-specific code path. Full walkthrough +
schema/API contracts: `specs/004-benchmark-harness/quickstart.md` and `.../contracts/`.

## Memory regime as config + verified provenance (spec 005)

The memory regime is **pure configuration**: select it per single run via `REGIME` (or `--regime`),
keeping prompts, action space, allowlist, budget, frozen split, and scoring identical — only the
memory shown to the agent changes. An unknown regime fails fast at startup (no silent default).

```bash
# run a member under a chosen regime (regime is the only thing that differs):
REGIME=recent_only RECENT_K=5 uv run ds-agent-loop --member wine --seed 0
REGIME=all_raw                 uv run ds-agent-loop --member wine --seed 0
REGIME=compacted_recent        uv run ds-agent-loop --member wine --seed 0
```

Provenance is verifiable on demand (no LLM calls) via the `ds-agent-memory` console script:

```bash
# verified replay: rebuild every decision's memory view from persisted history and assert its
# content hash matches what was shown (exit non-zero + named iteration on any mismatch):
uv run ds-agent-memory replay --cell wine|recent_only|s0|k3|m10
uv run ds-agent-memory replay --all

# cross-regime audit: prove two cells of the same (member, seed) differ ONLY in memory — equal
# config fingerprint (held-fixed factors, excluding regime/k/memory); fails loudly on contamination:
uv run ds-agent-memory audit --cell-a 'wine|recent_only|s0|k3|m10' --cell-b 'wine|all_raw|s0|k0|m10'
```

The config fingerprint is stamped into each cell's `repro` (and the export `cells.csv`); no new
tables or migration are added. Full walkthrough + API contract:
`specs/005-memory-regime-abstraction/quickstart.md` and `.../contracts/provenance-api.md`.

## The compaction operator: recorded cadence + lineage audit (spec 006)

The `compacted_recent` regime is backed by a **sanctioned, fully auditable** compaction operator
(Principle XII). On an explicit **cadence** `m` the outer loop projects the trajectory-so-far onto
the typed `DirectionalMemory` belief schema (the third sanctioned LLM job), seeing **only records
at or before the trigger** — never a future outcome. Every artifact now records, alongside its
source lineage:

- **`cadence`** — the explicit `m` in effect at that trigger (FR-004), and
- **`trigger_mode`** — `fixed` (exact cadence), `compact_over_what_exists` (a short window), or
  `token_threshold` (the optional off-cadence size trigger).

A **deterministic, no-LLM** lineage audit reconstructs, from persisted history, the exact set of
records at/before each artifact's trigger and asserts it equals the recorded `source_record_ids`.
It fails loudly if a future record leaked in, a record was silently omitted, or lineage disagrees
with history:

```bash
# audit a cell's compaction lineage against the raw trajectory (no LLM calls; non-zero on tamper):
uv run ds-agent-memory compaction 'wine|compacted_recent|s0|k3|m10'
# prints per artifact: trigger_iteration, cadence, trigger_mode, source count
# then: OK (n artifacts, 0 LLM calls)  — or each LineageMismatch (future_record_leaked /
#       record_omitted / history_disagreement) naming the artifact + offending record + iteration.
```

The single schema change is the additive, reversible **Alembic migration 0003** (`cadence` +
`trigger_mode` on `compaction_artifacts`; pre-006 rows read back `NULL` and are still audited). The
005 memory seam (`memory.build_view`), verified replay, and cross-regime audit are **unchanged**.
Full walkthrough + contracts: `specs/006-compaction-operator/quickstart.md`,
`.../contracts/lineage-audit-api.md`.

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
