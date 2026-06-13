# Implementation Plan: Benchmark Harness & Dataset Suite

**Branch**: `004-benchmark-harness` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-benchmark-harness/spec.md`

## Summary

Turn the existing in-memory benchmark scaffolding into a **fixed, versioned, Postgres-persisted
benchmark**. Feature 003 already shipped most of the *data shape*: `benchmark.py` has typed
`DatasetDescriptor`s, fully-offline loaders for both synthetic (delivery-time) and curated-real
(sklearn diabetes/wine/iris/breast-cancer) datasets, a 5-member default suite, a generic
descriptor-driven loop (`main.run_cell` → `train.score_on_split`, metric-direction aware, task-typed
allowlist) with **no delivery-time-special-casing**, and Alembic-managed schema. This feature closes
the four remaining gaps that make the benchmark a citable, reproducible artifact:

1. **Materialize splits + rows in Postgres with a content hash** (today splits are plain JSON under
   `state/splits/` and are a non-stratified shuffle). Add stratified splits for classification and
   persist `(member descriptor, split assignment, content hash)` via a new Alembic migration.
2. **Enforce versioning** — any change to a fixed factor (split, action space, allowlist, budget,
   metric) is rejected unless the `BENCHMARK_VERSION` is bumped; old versions stay attributable.
3. **Export** any member + its split rows to JSON/CSV that round-trips byte-identically.
4. **Idempotent re-materialization** — re-materializing an existing version is a no-op; a synthetic
   re-gen whose content hash diverges fails loudly.

The approach is **generalize + persist + version**, not a rewrite: extend `benchmark.py` and
`store.py`, add one Alembic migration, and keep the loop path unchanged.

## Technical Context

**Language/Version**: Python ≥ 3.11 (per `pyproject.toml`), run via `uv run`.

**Primary Dependencies**: scikit-learn (datasets, estimators, stratified split), pandas/numpy,
SQLAlchemy Core + Alembic (schema), Pydantic v2 / pydantic-settings (typed descriptors + config),
psycopg (Postgres driver). No new top-level dependency is required.

**Storage**: Single Postgres instance (`DATABASE_URL`); schema owned exclusively by Alembic
migrations under `alembic/versions/`. `state/` files remain an optional local mirror for debugging.

**Testing**: pytest. Offline unit tests for descriptors/splits/hash/versioning/export (`FakeStore`
or sqlite-free in-memory); a Postgres-backed integration test mirrors the existing
`test_store_integration.py` pattern (skipped when no DB).

**Target Platform**: Linux container; `docker compose up` brings up Postgres + runs `alembic upgrade
head` at startup (already wired in `store.upgrade_to_head`).

**Project Type**: Single `src`-layout research library (`src/ds_agent_loop/`) + thin `entrypoint/`.

**Performance Goals**: Datasets are small/moderate (≤ a few thousand rows); materializing the whole
suite is seconds. No throughput target — reproducibility and determinism dominate.

**Constraints**: Fully offline for the default suite (no network at materialization or run time);
deterministic under a fixed split seed; token usage MUST NOT scale with dataset size (synthetic
growth is Python-only); bounded agency unchanged (Principle III).

**Scale/Scope**: 5–6 suite members (regression + classification, synthetic + curated-real),
benchmark version `v1`.

## Constitution Check

*GATE: re-checked after design — PASS, no violations.*

- **Principle V (Fixed, versioned benchmark datasets)** — directly satisfied: frozen, stratified,
  content-hashed splits; synthetic data anchored to a fixed spec/seed generated in Python with no
  LLM calls; versioned suite with recorded changes. ✅
- **Principle III (Bounded agency)** — unchanged. Allowlist stays fixed, finite, task-typed; this
  feature only persists it. No new LLM job, no code execution. ✅
- **Principle IV (Inspectable & reproducible, Alembic-managed state)** — new tables ship as a single
  reviewed Alembic migration (`0002`); no operational `create_all`; everything exportable to
  JSON/CSV; `state/` mirror retained. ✅
- **Principle I (Simplicity)** — no new module is introduced; logic extends the existing
  `benchmark.py` (suite/splits/versioning/export) and `store.py` (persistence). No new framework. ✅
- **Principles VI/VIII/IX/X** — `uv` toolchain, Pydantic descriptors, replayable-from-persisted
  state, structured logging + container path all already in place and respected. ✅

No entry in Complexity Tracking — there are no justified violations.

## Project Structure

### Documentation (this feature)

```text
specs/004-benchmark-harness/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (splits, hashing, versioning, export)
├── data-model.md        # Phase 1 — descriptor, frozen split, member row, version record
├── quickstart.md        # Phase 1 — materialize / load / run / export the suite
├── contracts/
│   ├── db-schema.md      # benchmark_members + benchmark_splits tables (migration 0002)
│   └── benchmark-api.md  # benchmark.py public functions (materialize/load/export/version check)
└── checklists/
    └── requirements.md  # already present (passes)
```

### Source Code (repository root)

```text
src/ds_agent_loop/
├── benchmark.py     # EXTEND: stratified frozen_split, content_hash, materialize_suite(),
│                    #   load_member(), export_member(), version-drift check
├── store.py         # EXTEND: benchmark_members + benchmark_splits Table defs + upsert/read/export
├── train.py         # unchanged (generic score_on_split already metric/allowlist driven)
├── main.py          # unchanged (run_cell already descriptor-driven, no delivery-time path)
├── experiment.py    # minor: resolve descriptors via materialized suite by id
└── prompts.py       # unchanged (TaskType, descriptors)

alembic/versions/
└── 0002_benchmark_members_and_splits.py   # NEW migration (members + splits + version)

tests/
├── test_benchmark.py            # EXTEND: stratification, hash stability, version-drift reject
└── test_benchmark_persistence.py # NEW: materialize→load byte-identical, export round-trip, idempotency
```

**Structure Decision**: Single research library, extending existing modules. The benchmark logic
stays in `benchmark.py` (the constitution's sanctioned module) and persistence stays in `store.py`;
the only new files are one Alembic migration and one persistence test module — consistent with
Principle I's fixed single-purpose-module decomposition.

## Complexity Tracking

No constitution violations — table intentionally empty.
