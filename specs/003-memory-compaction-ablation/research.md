# Phase 0 Research: Memory-Compaction Ablation (Directional Research Memory)

**Feature**: `003-memory-compaction-ablation` | **Date**: 2026-06-13 | **Gate**: constitution v5.0.0

Resolves the planning-deferred items from the spec (dataset suite composition, budgets, `k`/`m`
defaults) plus the supporting technology choices the ablation harness needs.

## Decision 1 — Postgres access layer: SQLAlchemy Core + psycopg

**Decision**: Use **SQLAlchemy Core** (table metadata + `insert(...).on_conflict_do_update`), not
the ORM, over the **`psycopg` (v3)** driver. Tables defined once in `store.py`.

**Rationale**: Core gives typed, portable table definitions and idempotent upserts (needed for
resume, Principles IX/X) without the weight/indirection of an ORM (Principle I). psycopg3 is the
current, well-supported driver and works with the existing `postgres:17-alpine` compose service via
`DATABASE_URL`. JSON columns store the Pydantic models verbatim, keeping rows inspectable and
trivially exportable to JSON/CSV (FR-014a).

**Alternatives considered**: raw `psycopg` SQL strings (more error-prone, no schema object);
SQLAlchemy ORM (unnecessary mapping layer); an ORM like SQLModel (adds a dependency and indirection
for no gain at this scale). Rejected.

## Decision 2 — Test seam for persistence (hermetic, no network)

**Decision**: `store.py` depends on a SQLAlchemy `Engine` injected by the caller. Tests pass an
engine pointed at a disposable schema on the compose `db` when available, and otherwise an
in-process fake store implementing the same small interface. The offline `pytest` suite never
requires Vertex or a live DB.

**Rationale**: Keeps the constitution's "offline, hermetic, zero-network test suite" guarantee
(carried from 002) while still unit-testing persistence/resume logic. The store interface is small
(upsert cell, append record, save view, save artifact, log, export), so a fake is cheap.

**Alternatives considered**: SQLite-backed tests (dialect drift from Postgres `on_conflict`,
JSON semantics differ); testcontainers (adds Docker dependency to the unit suite). Rejected for the
unit layer; a single integration test MAY run against the compose `db`.

## Decision 3 — Structured logging to stdout + Postgres

**Decision**: stdlib `logging` with a JSON-lines formatter to stdout, plus a lightweight DB handler
that inserts into a `run_logs` table keyed by `(cell_id, iteration, level, event, ts, payload)`.
One `get_logger(cell_id)` helper binds the cell context.

**Rationale**: Satisfies Principle X (leveled, machine-parseable, lifecycle + per-iteration +
LLM/persistence + failures; emitted to stdout AND retrievable from Postgres) with stdlib only — no
logging framework (Principle I). Querying `run_logs` makes a run diagnosable after the fact without
a rerun.

**Alternatives considered**: `structlog`/`loguru` (extra dep, not needed); logs only to files
(not queryable per X). Rejected.

## Decision 4 — Benchmark dataset suite (offline, deterministic, fixed splits)

**Decision**: Ship a versioned suite of **6 small tabular datasets** baked into `benchmark.py`,
all loadable offline and deterministically split once into train/val/test:

| id | task | source | primary metric (direction) |
|----|------|--------|----------------------------|
| `delivery_time` | regression | existing synthetic (anchored `data_spec`) | RMSE (↓) |
| `diabetes` | regression | `sklearn.datasets.load_diabetes` | RMSE (↓) |
| `california_housing` | regression | `fetch_california_housing` (subsampled, cached) | RMSE (↓) |
| `breast_cancer` | classification | `load_breast_cancer` | macro-F1 (↑) |
| `wine` | classification | `load_wine` | macro-F1 (↑) |
| `adult_income` (opt.) | classification | OpenML cached / synthetic fallback | macro-F1 (↑) |

Splits are produced by a fixed split seed and **persisted** (indices saved), reused byte-for-byte
across every regime/seed/`k`/`m` (FR-017, SC-002). The suite carries a `benchmark_version` string
stamped onto every cell (Principle IX). The synthetic `delivery_time` task is the dev/smoke dataset.

**Rationale**: scikit-learn built-ins are offline, license-clean, small enough for a full sweep on
one machine, and mix regression + classification (Principle V; FR-016). Caching any `fetch_*`
download keeps reruns offline and deterministic.

**Alternatives considered**: large OpenML/Kaggle suites (slow, network, non-deterministic);
synthetic-only (weaker external validity). A subsample + cache of one larger set is the compromise.

## Decision 5 — Model allowlist widened to classifiers

**Decision**: Add `CLASSIFIER_ALLOWLIST` (`LogisticRegression`, `RandomForestClassifier`,
`GradientBoostingClassifier`, `HistGradientBoostingClassifier`) alongside the existing
`MODEL_ALLOWLIST` regressors. `train.py` selects the allowlist by the dataset's task type;
validation/rejection logic is shared. Baseline per task type: `LinearRegression` / `LogisticRegression`.

**Rationale**: v5.0.0 Principle III explicitly widens the allowlist to classifiers; the set stays
fixed, finite, developer-owned, and validated before training (bounded agency preserved).

## Decision 6 — Generic scoring with fixed train/val/test splits

**Decision**: Replace the hard-coded delivery-time columns + 5-fold CV in `train.py` with a generic
path driven by the `DatasetDescriptor` (feature schema, target, task type) that fits on **train**,
selects/early-acceptance on **validation**, and reports the frozen **test** metric for the primary
outcome (FR-019). One-hot for declared categoricals; metric-aware scoring (RMSE↓ regression;
macro-F1↑ classification) with correct optimization direction (FR-023).

**Rationale**: Fixed splits (not CV) are required so the same split is reused across regimes for a
fair paired comparison (Principle V, XIII; SC-002) and so a held-out test number anchors the
primary outcome.

**Alternatives considered**: keep CV (can't pin an identical split across cells cleanly, and mixes
val/test). Rejected.

## Decision 7 — Directional Research Memory: schema + third LLM call

**Decision**: Add a `DirectionalMemory` Pydantic model + `COMPACTION_SCHEMA` with the required
belief fields (confirmed_findings, failed_directions, promising_directions, best_known_configs,
unresolved_questions, next_step_recommendation, confidence, rationale) — FR-007, Principle XII.
`llm.request_compaction()` reuses `_run_structured` (tool-less ADK agent, `output_schema`), making
compaction the **third** sanctioned structured-JSON job (Principle II). `compaction.py` owns the
outer loop: trigger at every `m` experiments over source records at/before the trigger only (no
future leakage, FR-008/SC-005), persist artifact + source lineage, reuse unchanged until next
trigger. Schema-invalid artifact → fail fast (FR-010).

**Rationale**: Pins the thesis's central operator to an inspectable belief schema and an explicit
outer loop (Principle XII), inside the existing bounded-agency machinery.

## Decision 8 — Memory regime interface + exact-view provenance

**Decision**: `memory.build_view(regime, history, k, latest_artifact) -> MemoryView` is the single
seam behind all three regimes (config, not forks — Principle XIII). The returned `MemoryView`
carries both the rendered prompt text and the **identifiers** of every record/artifact included;
`store.py` persists the exact view per decision (content + content-hash ref) so any decision is
replayable and regimes are auditable against each other (FR-013, IX). Early-history edge cases
(fewer than `k`, pre-first-compaction) handled deterministically and logged (spec Edge Cases).

## Decision 9 — Statistics & plots

**Decision**: `scipy.stats` for paired tests (Wilcoxon signed-rank default, paired-t option) and
percentile bootstrap CIs for effect sizes across the per-dataset paired structure (FR-021);
`matplotlib` for improvement curves, token-growth curves, and per-dataset paired-difference plots
(FR-022). Secondary outcomes (AUC-of-improvement, improving-steps, iters-to-90%, repetition rate,
search diversity, prompt-token count) computed in `analysis.py`, metric-direction-aware (FR-020/023).

**Rationale**: scipy/matplotlib are the minimal, standard tools for paired significance + curves;
no heavier stats/plotting stack needed (Principle I).

## Decision 10 — Budgets & defaults (pre-registered)

**Decision**: Defaults (overridable via Settings/CLI, recorded per cell): budget `N = 30` iters/cell;
seeds `{0,1,2,3,4}` (5); recent window `k = 5`; compaction cadence `m = 10`. US5 grid defaults
`k ∈ {3,5,10}`, `m ∈ {5,10,20}`. Token-threshold trigger `t` (FR-024) optional, off by default.

**Rationale**: Matches the experiment protocol's starting points; small enough for a full offline
sweep, large enough to expose the all-raw degradation the phase-transition analysis targets (XIV).

## Open items for `/speckit-tasks`

- Finalize whether `adult_income` ships in v1 of the suite or is deferred (keeps the sweep small).
- Confirm the single integration test against the compose `db` vs. fake-only unit tests.
- Confirm `benchmark_version` bump policy when a dataset/split changes (Principle V).
