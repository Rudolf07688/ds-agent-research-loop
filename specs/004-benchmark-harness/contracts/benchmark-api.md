# Contract: `benchmark.py` public API (extended)

Existing functions (feature 003) — unchanged signatures:

- `load_dataset(dataset_id) -> pd.DataFrame` — deterministic, offline for default suite.
- `get_descriptor(dataset_id) -> DatasetDescriptor`.
- `suite(dataset_ids=None) -> list[DatasetDescriptor]`.
- `frozen_split(dataset_id, *, n_rows=None, state_dir=None) -> dict[str, list[int]]` — **extended**
  to stratify classification members and to compute/return a content hash (see below); keeps the
  `state/splits/*.json` mirror.

New / extended for feature 004:

## `content_hash(dataset_id, version, split) -> str`
sha256 over the canonical JSON of `(dataset_id, version, {train,val,test sorted})`. Stable across
processes (SC-003).

## `frozen_split(...) -> FrozenSplit`
Returns indices + `content_hash` + `stratified`. Classification ⇒ two-stage
`train_test_split(stratify=y)` under `SPLIT_SEED`; rejects a member whose split would drop a class
or leave a partition empty (edge cases). Regression keeps the fixed-seed shuffle.

## `materialize_suite(store, dataset_ids=None, *, version=BENCHMARK_VERSION) -> list[DatasetDescriptor]`
For each member: build descriptor, compute split + hash + fingerprint, **upsert** into
`benchmark_members` / `benchmark_splits` keyed by `(dataset_id, version)`. Idempotent: an existing
row whose hash/fingerprint differs ⇒ raise loudly (FR-019, FR-014). Returns the materialized
descriptors.

## `load_member(store, dataset_id, *, version=BENCHMARK_VERSION) -> tuple[DatasetDescriptor, FrozenSplit, pd.DataFrame]`
Loads persisted descriptor + split, regenerates rows via the deterministic loader, and **asserts**
the content hash matches the persisted one (byte-identical reuse, SC-001/003). No test-row leakage:
the split assignment is read, never re-drawn.

## `export_member(store, dataset_id, out_dir, *, version=BENCHMARK_VERSION) -> Path`
Writes `descriptor.json` + `rows.csv` + `split.json` under
`out_dir/<version>/<dataset_id>/`; reload round-trips to byte-identical data and re-asserts the hash
(FR-018, SC-006).

## `check_version_drift(store, descriptor, *, version=BENCHMARK_VERSION) -> None`
Recomputes the member fingerprint and compares to the persisted one under `version`; mismatch raises
unless `version` is new (FR-014, SC-005).

## Errors
- `BenchmarkDriftError` — content-hash or fingerprint mismatch under an existing version.
- `SplitError` — empty/degenerate partition, or class dropped by a classification split.
Both fail fast and loud (Principle X).
