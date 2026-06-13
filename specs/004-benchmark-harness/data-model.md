# Phase 1 Data Model: Benchmark Harness & Dataset Suite

Typed entities (Pydantic v2, `extra="forbid"`) and their Postgres persistence. The descriptor model
already exists in `benchmark.py`; this feature adds the persisted split/member rows and a version
fingerprint.

## DatasetDescriptor (exists — `benchmark.py`)

One benchmark member's fixed factors.

| Field | Type | Notes |
|-------|------|-------|
| `dataset_id` | str | stable id, suite-unique |
| `task_type` | TaskType | `regression` \| `classification` |
| `feature_schema` | dict[str,str] | column → `numeric` \| `categorical` |
| `target` | str | target column |
| `primary_metric` | str | `rmse` (reg) \| `macro_f1` (clf) |
| `metric_direction` | int | `+1` higher-better, `-1` lower-better |
| `split_ref` | str | `f"{dataset_id}-{benchmark_version}"` |
| `benchmark_version` | str | default `BENCHMARK_VERSION` |
| `feature_names` | list[str] | ordered features |

**Add (this feature)**: `provenance` (`anchored_synthetic` \| `curated_real`), `budget` (int `N`),
`patience` (int `k` \| null), `action_space` (list[str], frozen), `model_allowlist` (list[str],
derived from `allowlist_for(task_type)` — persisted explicitly so drift is detectable).

**Validation**: classification ⇒ metric is a classification metric (direction `+1`) and allowlist ⊆
classifiers; regression ⇒ regression metric (direction `-1`) and allowlist ⊆ regressors. A
metric/task-type or allowlist/task-type mismatch is rejected at declaration (edge case).

## FrozenSplit (extend — `benchmark.py`)

Fixed assignment of row indices to partitions, content-hashed.

| Field | Type | Notes |
|-------|------|-------|
| `dataset_id` | str | |
| `benchmark_version` | str | |
| `train` / `val` / `test` | list[int] | disjoint row-index lists; union = all rows |
| `content_hash` | str | sha256 over canonical `(dataset_id, version, sorted partitions)` |
| `stratified` | bool | true for classification |

**Rules**: disjoint partitions, no empty partition (rejected at declaration — edge case), no test
leakage; classification stratified so every class appears in every partition (else flagged at
materialization). Computed once under `SPLIT_SEED`; reload asserts `content_hash`.

## BenchmarkVersion / fingerprint (new — `benchmark.py`)

| Field | Type | Notes |
|-------|------|-------|
| `benchmark_version` | str | e.g. `v1` |
| `member_fingerprints` | dict[str,str] | `dataset_id` → sha256 of fixed factors |

A change to any fixed factor changes the fingerprint; materialization under an existing version
asserts equality and rejects drift without a version bump (FR-014).

## Persistence (new tables — Alembic migration 0002)

### `benchmark_members`
PK `(dataset_id, benchmark_version)`. Columns: `task_type`, `provenance`, `target`,
`primary_metric`, `metric_direction`, `budget`, `patience`, `feature_schema` (JSONB),
`feature_names` (JSONB), `action_space` (JSONB), `model_allowlist` (JSONB), `fingerprint`,
`created_ts`.

### `benchmark_splits`
PK `(dataset_id, benchmark_version)`. Columns: `train_idx` (JSONB), `val_idx` (JSONB), `test_idx`
(JSONB), `content_hash`, `stratified` (bool), `n_rows`, `created_ts`.

Keying both tables by `(dataset_id, benchmark_version)` lets a new version coexist with the old so
prior results stay attributable (FR-014, US3). Idempotent upsert: existing row ⇒ assert hash match.

## State transitions

`declared → materialized (members+splits persisted, hashed) → loadable-by-id → exported`.
Re-materialize: hash match ⇒ no-op; mismatch ⇒ loud failure (FR-019, SC-007).
