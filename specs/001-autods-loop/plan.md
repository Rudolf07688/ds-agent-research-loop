# Implementation Plan: LLM Autonomous Data Scientist (Toy) Loop

**Branch**: `001-autods-loop` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-autods-loop/spec.md`

## Summary

Build a small, flat Python repo where an LLM bootstraps a seed delivery dataset plus a
reusable generation spec (one structured-JSON call), and proposes the next experiment
step (structured-JSON call) by reasoning over recorded metrics. Python owns everything
else: local dataset expansion from the fixed seed spec, training/evaluating one
scikit-learn regressor per iteration, recording run history, tracking the best run, and
looping for `N` iterations with an early-stop on no improvement. Safety is enforced in
Python via a model allowlist, hyperparameter validation, and JSON-config-only LLM
authority (no code execution).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: scikit-learn (models + evaluation), an LLM SDK supporting
structured/JSON-schema-constrained output (OpenAI-style client), pandas/numpy for data
handling, pydantic + pydantic-settings (typed entities + centralized config), python-dotenv
for loading `.env`. Managed by `uv` (declared in `pyproject.toml`, pinned in `uv.lock`);
kept minimal.

**Storage**: Plain files under `state/` — `data_spec.json`, `seed_rows.json`,
`dataset.csv`, `history.json`, `best_run.json`; human-readable run summary under
`outputs/run_summary.txt`. No database.

**Testing**: pytest (run as `uv run pytest`) for the pure-Python units that do not
require an LLM call (spec expansion, hyperparameter/model validation, history append,
best-run selection, stop-condition logic). LLM calls are not part of the automated test
loop.

**Target Platform**: Local developer machine (macOS/Linux), offline except for the LLM
API calls.

**Project Type**: Single project — small CLI-driven script (`main.py`) with a handful of
single-purpose modules.

**Performance Goals**: Not a performance project. Hard constraint: per-run token usage
MUST NOT scale with dataset size (expansion is local). A full `N`-iteration toy run
completes in minutes on a laptop.

**Constraints**: Exactly two LLM JSON schemas (seed-generation, next-step). LLM may only
choose from an allowlist of regressors and may only emit JSON config — never executable
code. All hyperparameters validated before training. Dataset expansion always anchors to
the original saved spec, never a regenerated one. I/O-bound LLM calls use asyncio where
it adds value (sync CPU-bound training is fine); the code stays callable/non-CLI-bound so
a future FastAPI service is possible, but building that service is OUT OF SCOPE now.

**Scale/Scope**: Toy. Single user, offline, ~8 source files, a few hundred to a few
thousand synthetic rows, a handful (≤4) of candidate regressors, small `N`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates derived from `.specify/memory/constitution.md` v1.0.0:

- **I. Simplicity & Readability First** — PASS. Flat layout (`llm.py`, `data_gen.py`,
  `train.py`, `history.py`, `prompts.py`, `main.py`), no frameworks, no agent
  orchestration, no DB/UI/workers. Single project structure.
- **II. Constrained LLM Contracts (Structured JSON Only)** — PASS. Exactly two schemas;
  the LLM has only the two sanctioned jobs; no free-form parsing; next-step `action` is
  an enum.
- **III. Bounded Agency (No Arbitrary Code Execution)** — PASS. Model allowlist,
  JSON-config-only proposals, Python-side hyperparameter validation, rejection of any
  non-conforming/ code output. Enforced in `train.py`/validation before training.
- **IV. Inspectable & Reproducible State** — PASS. All durable state is human-readable
  files under `state/`; full history fields recorded; best run persisted separately;
  seed/spec generation skipped when valid state exists (checkpoint resume).
- **V. Anchored Synthetic Data Generation** — PASS. Expansion derives all rows from the
  original saved `data_spec`; no recursive regeneration; token usage independent of
  dataset size.
- **VI. uv-Managed Python Environment** — PASS. Deps via `uv` (`pyproject.toml`/
  `uv.lock`); all scripts run via `uv run python ...`.
- **VII. Progress Communicated via notes/** — PASS. HTML progress snapshot written to
  `notes/` at section completion/break; `notes/` kept current.
- **VIII. Typed Models & Centralized Settings (Pydantic)** — PASS. Entities (data spec,
  run/history record, best run, next-step decision) modeled with Pydantic; runtime config
  is one `pydantic-settings` Settings object. Kept to a few focused models (Principle I).

No violations. Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-autods-loop/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (LLM JSON schemas + config/CLI contract)
│   ├── seed_generation.schema.json
│   ├── next_step.schema.json
│   └── cli.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
llm-autods-toy/                 # repo root (this project)
├── README.md
├── pyproject.toml              # uv-managed dependencies
├── uv.lock
├── .env.example
├── main.py                     # the loop: seed → expand → train → next-step → record
├── llm.py                      # thin LLM wrapper; two structured-JSON calls only
├── data_gen.py                 # seed handling + local expansion from saved data_spec
├── train.py                    # feature prep, model registry/allowlist, train, score
├── history.py                  # append runs, track/update best run
├── prompts.py                  # prompt text + JSON schema definitions
├── state/
│   ├── data_spec.json
│   ├── seed_rows.json
│   ├── dataset.csv
│   ├── history.json
│   └── best_run.json
└── outputs/
    └── run_summary.txt

tests/
├── test_data_gen.py            # expansion stays anchored to saved spec; no LLM call
├── test_train.py               # allowlist + hyperparameter validation; scoring
├── test_history.py             # history append + best-run selection
└── test_loop.py                # stop conditions (N iterations, no-improvement-for-k)
```

**Structure Decision**: Single flat project at the repo root, matching the spec's repo
layout exactly. Each module has one responsibility; `main.py` is the only orchestrator.
A sibling `tests/` directory holds pytest units for the pure-Python logic (no LLM in the
automated loop). This satisfies Constitution Principle I (simplicity) — no `src/`
package nesting, no service/abstraction layers.

## Complexity Tracking

> No constitution violations — no entries required.
