# Implementation Plan: Memory-Compaction Ablation — Directional Research Memory (A/B/C)

**Branch**: `003-memory-compaction-ablation` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-memory-compaction-ablation/spec.md`

## Summary

Turn the single-run AutoDS loop into a controlled **memory-regime ablation** across a versioned
benchmark of tabular datasets. Exactly one variable is manipulated — the slice of prior experiment
history the agent sees before each decision — across three regimes: **recent-only** (last `k` raw
records), **all-raw** (full history), and **compacted+recent** (one **Directional Research Memory**
artifact + last `k` raw records). The compaction artifact is the project's central object
(Constitution Principle XII): a schema-constrained projection of the raw trajectory onto stable
beliefs (confirmed findings / failed directions / promising directions / best-known configs /
unresolved questions / next-step), produced by a sanctioned **third** LLM call on a fixed outer-loop
cadence `m`. A cell orchestrator runs every `(dataset × regime × seed [× k × m])` cell to a fixed
budget, persists everything to **Postgres** (with JSON/CSV export), keeps runs **replayable** and
**resumable**, emits **structured logs to stdout + Postgres**, and an analysis step produces paired
significance tests, effect-size CIs, threshold curves, and trajectory/diversity metrics that make
the directional/momentum claim evaluable.

This plan gates against **constitution v5.0.0** (Directional Research Memory thesis). The spec was
authored under earlier vocabulary ("memory strategy", "compaction artifact"); it is substantively
v5.0.0-aligned, and this plan adopts the v5.0.0 terms in the data model and contracts.

## Technical Context

**Language/Version**: Python 3.13 (inherited from feature 002; `requires-python >=3.11`).

**Primary Dependencies**: existing — `google-genai`, `google-adk`, scikit-learn, pandas, numpy,
pydantic, pydantic-settings. **Added**: `SQLAlchemy` (Core, no ORM) + `psycopg[binary]` (Postgres
driver), `scipy` (Wilcoxon / paired-t / bootstrap), `matplotlib` (curves & paired-difference plots).

**Storage**: Single **Postgres** instance (`postgres:17-alpine`, already in `docker-compose.yml`)
as the durable home of cells, experiment records, memory views, compaction artifacts (+ lineage),
and structured logs — reached via `DATABASE_URL`. All of it exportable to human-readable JSON/CSV
under `state/` / `outputs/`; the single-dataset dev path may still mirror `state/*.json`
(Principle IV).

**Testing**: `pytest`, offline/hermetic — stubbed ADK/genai agent (zero network) and a store seam
that runs against the compose `db` or an in-process fake (research Decision 2). Deterministic
machinery (splits, scoring, memory-view construction, compaction parsing, paired stats, export,
resume) is unit-tested (Principle XI).

**Target Platform**: Local (uv) and the Linux container; full sweeps run via `docker compose up`
(Principle X).

**Project Type**: Single `src`-layout library (`src/ds_agent_loop/`) + thin `entrypoint/` consumer.

**Performance Goals**: Offline-feasible on one machine. Token cost still independent of dataset size
(local expansion, Principle V). all-raw prompt-token growth is *recorded as a measured outcome*
(SC-006), not optimized away.

**Constraints**: Memory regime is the ONLY manipulated variable, with the exact memory shown
persisted per decision (Principle XIII); bounded agency preserved — compaction is a third
*structured-JSON* call, never code (Principles II, III, XII); fixed per-dataset train/val/test
splits reused across all cells (Principle V); idempotent persistence so resume neither duplicates
nor corrupts (Principles IX, X).

**Scale/Scope**: 5–10 datasets × 3 regimes × multiple seeds × fixed budget (≈30 iters), optional
`(k, m)` grid (US5). Single operator, batch job.

## Constitution Check

*GATE: evaluated against constitution **v5.1.0**.* (v5.1.0 adds one Development-Workflow practice —
repository navigation and pre-change impact analysis MUST go through the GitNexus MCP tools before
any larger change; this applies during implementation, not to this planning artifact, and does not
alter any principle gate below.)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity & Readability First | ✅ Pass | New modules (`memory.py`, `compaction.py`, `benchmark.py`, `store.py`, `experiment.py`, `analysis.py`) are exactly the benchmark/regime/compaction decomposition v5.0.0 Principle I anticipates; each is single-purpose and concretely required. No new agent framework; the ADK agent stays minimal. Added deps justified per-use in research.md. |
| II. Constrained LLM Contracts (Structured JSON) | ✅ Pass | Adds the **third sanctioned job** — compaction — explicitly permitted by v5.0.0 II/XII. New `COMPACTION_SCHEMA` + `DirectionalMemory` model, validated via the same `_run_structured` path; malformed → fail fast (FR-010). Action space unchanged & identical across regimes. |
| III. Bounded Agency (No Code Execution) | ✅ Pass | Allowlist **widened to classifiers** (v5.0.0 III) via a new `CLASSIFIER_ALLOWLIST`; still fixed, finite, developer-owned, validated before training. Compaction agent is tool-less, emits JSON only. |
| IV. Inspectable & Reproducible State | ✅ Pass | Postgres is the documented durable store; schema in `contracts/db-schema.md`; full JSON/CSV export (FR-014a). Per-cell keys; resumable. |
| V. Fixed, Versioned Benchmark Datasets | ✅ Pass | Versioned suite (regression + classification), frozen train/val/test splits reused across all cells/seeds (FR-016/017); synthetic delivery-time task is one anchored member; token cost stays dataset-size-independent. |
| VI. uv-Managed Python Environment | ✅ Pass | New deps added via `uv`; everything runs via `uv run …`. |
| VII. Progress via notes/ | ✅ Pass | HTML progress snapshot + analysis summary written under `notes/` (FR-022). |
| VIII. Typed Models & Centralized Settings | ✅ Pass | New Pydantic models (DirectionalMemory, MemoryView, DatasetDescriptor, ExperimentCell, OutcomeSummary); all new config on the single `Settings` object. |
| IX. Reproducible & Replayable Experiments | ✅ Pass | Cells stamped with commit/settings/benchmark-version/dataset+split/seed/regime+params; deterministic steps reproducible; resume without recompute or new LLM calls (FR-014, SC-007). |
| X. Operational Reliability & Observability | ✅ Pass | Structured JSON-lines logs to stdout **and** Postgres (`run_logs`); `docker compose up` runs a sweep to completion + correct exit; failures loud & per-cell isolated (FR-015); idempotent upserts. Closes the current "app does not yet read from Postgres" gap. |
| XI. Research Rigor & Whitepaper Outcome | ✅ Pass | Methodology pre-registered in this spec (H1–H3, fixed factors, metrics, budgets, analysis plan); every reported number regenerable from persisted runs; tests for deterministic machinery required. |
| XII. Directional Research Memory | ✅ Pass | Compaction artifact = the belief-schema projection (true/failed/unresolved/directions) with the required fields; **outer compaction loop** at recorded cadence `m`; source→artifact lineage persisted; no future-outcome leakage (FR-008, SC-005). |
| XIII. Memory as the Controlled Experimental Variable | ✅ Pass | One `memory.py` interface behind the three regimes (config, not forks); everything else byte-for-byte fixed per (dataset, seed) (FR-005, SC-002); the **exact memory view** shown is persisted per decision (FR-013). |
| XIV. Benchmark, Ablation & Phase-Transition Analysis | ✅ Pass | Multi-dataset, multi-seed, paired tests + bootstrap CIs (FR-021); trajectory/diversity/regret-style outcomes (FR-020); `(k, m)` threshold sweep for the phase transition (FR-025, US5); null results reported faithfully. |

**Result**: **PASS** — no violations. One **non-blocking terminology note**: the spec uses
"memory strategy / compaction artifact"; this plan, the data model, and contracts adopt the v5.0.0
terms "memory **regime** / **Directional Research Memory**". Recommend a light `/speckit-specify`
reword of 003 to converge vocabulary (does not change scope). Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/003-memory-compaction-ablation/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (persistence, logging, dataset suite, stats, regimes)
├── data-model.md        # Phase 1 — entities (DirectionalMemory, MemoryView, Cell, Descriptor, …)
├── quickstart.md        # Phase 1 — run one cell, run the sweep, export, analyze
├── contracts/
│   ├── compaction-schema.md     # The Directional Research Memory JSON schema (third LLM job)
│   ├── memory-view.md           # Regime → exact-memory-view contract + provenance
│   ├── db-schema.md             # Postgres tables + JSON/CSV export mapping
│   └── runner-cli.md            # Sweep/cell/analyze CLI + settings contract
├── checklists/
│   └── requirements.md  # (exists)
└── tasks.md             # Phase 2 — created by /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
src/ds_agent_loop/
├── __init__.py          # export run surface (run_cell, run_sweep, Settings)
├── prompts.py           # MODIFY: + DirectionalMemory model + COMPACTION_SCHEMA + compaction prompts;
│                        #          + benchmark/regime/db Settings fields; existing schemas unchanged
├── llm.py               # MODIFY: + request_compaction() (third sanctioned structured call; reuse _run_structured)
├── data_gen.py          # unchanged (synthetic delivery-time member of the suite)
├── train.py             # MODIFY: + CLASSIFIER_ALLOWLIST; generic feature schema + fixed train/val/test
│                        #          split scoring (replaces hard-coded delivery columns / CV); metric-aware
├── history.py           # MODIFY: RunRecord gains dataset_id/condition/seed/k/m/memory_view_ref/token_count
├── benchmark.py         # NEW: DatasetDescriptor suite, frozen splits, per-dataset primary metric+direction
├── memory.py            # NEW: regime interface → MemoryView (recent-only/all-raw/compacted+recent) + provenance
├── compaction.py        # NEW: outer compaction loop — trigger at cadence m, build artifact, persist lineage
├── store.py             # NEW: Postgres (SQLAlchemy Core) — cells/records/views/artifacts/logs; JSON/CSV export;
│                        #       structured-log sink; idempotent upserts + resume
├── experiment.py        # NEW: cell orchestrator (dataset × regime × seed × k × m); per-cell isolation/resume
├── analysis.py          # NEW: primary/secondary outcomes, paired tests + bootstrap CIs, curves/plots, notes/
└── main.py              # MODIFY: parameterize run_loop into run_cell(descriptor, regime, seed, …); CLI thin

entrypoint/
├── run.py               # MODIFY: invoke the sweep (or a single cell) as the container's batch job
├── config.py            # MODIFY if it references changed fields
└── smoke_live.py        # unchanged (manual live verify)

tests/                   # ADD: test_memory.py, test_compaction.py, test_benchmark.py, test_store.py,
│                        #       test_experiment.py, test_analysis.py; MODIFY test_train.py (classifiers+splits)
pyproject.toml           # MODIFY: + sqlalchemy, psycopg[binary], scipy, matplotlib
docker-compose.yml       # MODIFY: backend now reads DATABASE_URL (remove "does not yet read" note); run sweep
.env.example             # MODIFY: + benchmark/regime/k/m/seeds/DATABASE_URL knobs
README.md                # MODIFY: regimes, Directional Research Memory, sweep/export/analyze workflow
```

**Structure Decision**: Keep the single `src`-layout library + thin `entrypoint/` consumer. The
ablation is added as focused single-purpose modules (the exact `memory.py`/`compaction.py`/
`benchmark.py` decomposition v5.0.0 names), with `store.py`/`experiment.py`/`analysis.py` for
persistence, orchestration, and reporting. The per-iteration agent contract and the two existing
schemas are unchanged; `train.py` is generalized (classifiers + fixed splits) and `main.py`'s loop
is parameterized into a reusable `run_cell` that `experiment.py` sweeps.

## Complexity Tracking

> No constitution violations — section intentionally empty. Added modules and dependencies are the
> minimum the benchmark, the three regimes, the Directional Research Memory operator, Postgres
> persistence/observability, and the paired statistical analysis concretely require; each is
> justified per-use in research.md and admitted by v5.0.0 Principles I, III, V, X, XII–XIV.
