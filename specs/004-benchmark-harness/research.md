# Phase 0 Research: Benchmark Harness & Dataset Suite

All Technical Context items were resolvable from the existing codebase (feature 003 already built
the descriptor/loader/loop layer) and the constitution. No `NEEDS CLARIFICATION` remains.

## Decision 1 — Split materialization: Postgres rows + content hash (replaces file-only JSON)

- **Decision**: Persist each member's frozen split as `benchmark_splits` rows in Postgres carrying
  the per-partition row-index lists and a `content_hash` over the canonical
  `(dataset_id, version, sorted partition→indices)` payload. Keep the `state/splits/*.json` mirror
  for cheap local debugging.
- **Rationale**: FR-008/009/017 require Postgres persistence + verifiable byte-identical reuse;
  today `benchmark.frozen_split` writes only `state/splits/*.json` with no hash. The hash makes
  drift detectable (SC-007) and lets a reload assert identity.
- **Alternatives rejected**: (a) Hash-only without storing rows — can't reconstruct the split for
  export. (b) Store full feature rows per split — redundant, since members load deterministically;
  store row *indices* + the content hash and regenerate rows via the deterministic loader, asserting
  the hash on reload.

## Decision 2 — Stratified splits for classification

- **Decision**: Use `sklearn.model_selection.train_test_split(..., stratify=y)` (two-stage:
  train vs temp, then val vs test) for classification members; keep the existing fixed-seed shuffle
  for regression. Seed is the suite-wide `SPLIT_SEED`.
- **Rationale**: FR-009 / edge case "class imbalance" require all classes present in every partition;
  the current plain `rng.shuffle` does not guarantee that. A member whose split cannot preserve all
  classes is flagged at materialization, not run time.
- **Alternatives rejected**: Manual per-class index bucketing — `train_test_split(stratify=)` is the
  standard, deterministic-under-seed, and already a dependency.

## Decision 3 — Versioning enforcement via a recorded fingerprint

- **Decision**: Each member's fixed factors (task type, metric+direction, action space, allowlist,
  budget, split policy) are fingerprinted; materialization under an existing `BENCHMARK_VERSION`
  asserts the stored fingerprint matches. A divergence without a version bump is rejected loudly;
  a new version coexists with the old (rows keyed by `(dataset_id, benchmark_version)`).
- **Rationale**: FR-013/014, SC-005, US3 — drift must not be silently absorbed and old results must
  stay attributable. Keying persisted rows by `(dataset_id, version)` keeps prior versions intact.
- **Alternatives rejected**: Trusting the `BENCHMARK_VERSION` constant alone — it wouldn't catch an
  accidental factor change under the same version string.

## Decision 4 — Export round-trips via descriptor + indices, regenerated rows

- **Decision**: `export_member` writes the member descriptor (JSON) + the split assignment and the
  materialized rows (CSV) to `outputs/benchmark/<version>/<dataset_id>/`. Re-import reloads the
  descriptor + rows and asserts the content hash, guaranteeing byte-identical round-trip.
- **Rationale**: FR-018, SC-006 require human-readable, DB-free reuse and byte-identical reload.
- **Alternatives rejected**: Postgres-dump export — not human-readable and couples reuse to a DB.

## Decision 5 — Idempotent materialization

- **Decision**: `materialize_suite` upserts members/splits keyed by `(dataset_id, version)`; if a row
  exists, the recomputed content hash must equal the stored one (no-op on match, loud failure on
  mismatch). Synthetic regeneration uses the fixed seed so a match is expected.
- **Rationale**: FR-019, SC-007 — re-materialization neither duplicates nor corrupts, and detects
  silent data drift.
- **Alternatives rejected**: Delete-and-reinsert — would destroy prior-version attribution and mask
  drift.

## Decision 6 — No new module, no new dependency, loop unchanged

- **Decision**: Extend `benchmark.py` (suite/splits/version/export) and `store.py` (tables + I/O);
  add one Alembic migration `0002`. The loop (`main.run_cell`, `train.score_on_split`) is already
  descriptor-driven and metric/allowlist-aware — no change needed for FR-015/016 beyond resolving the
  descriptor from the materialized suite.
- **Rationale**: Principle I (fixed module decomposition) and the spec's "generalize, not rewrite"
  assumption. Verified by reading `main.py`/`train.py`: `run_cell` takes a `DatasetDescriptor`, uses
  `allowlist_for(task_type)`, `descriptor.metric_direction`, and `score_on_split` on the frozen split
  with no `delivery_time` branch.
- **Alternatives rejected**: A new `suite.py`/`materialize.py` module — unjustified per YAGNI;
  benchmark concerns already live in `benchmark.py`.
