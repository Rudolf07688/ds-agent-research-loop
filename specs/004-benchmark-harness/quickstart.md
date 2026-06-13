# Quickstart: Benchmark Harness & Dataset Suite

All commands run via `uv` (Principle VI). Postgres comes from the root `docker-compose.yml`;
`alembic upgrade head` runs at startup (`store.upgrade_to_head`).

## 1. Apply the schema (migration 0002)

```bash
uv run alembic upgrade head        # creates benchmark_members + benchmark_splits
```

## 2. Materialize the versioned suite

```bash
uv run python -m ds_agent_loop.benchmark materialize     # or via entrypoint/run.py
```

Persists 5–6 members (regression + classification, synthetic + curated-real) under
`BENCHMARK_VERSION=v1` with stratified, content-hashed frozen splits. Idempotent: re-running is a
no-op unless data drifts (then it fails loudly).

## 3. Load a member by id (byte-identical across processes)

```python
from ds_agent_loop import benchmark, store
s = store.Store(database_url, create=False)
descriptor, split, df = benchmark.load_member(s, "wine")     # classification member
# split.content_hash equals the persisted hash; all classes present in train/val/test
```

## 4. Run the existing loop against any member by id

```bash
uv run python -m ds_agent_loop.main --dataset diabetes   --seed 0   # regression
uv run python -m ds_agent_loop.main --dataset breast_cancer --seed 0 # classification
```

The loop uses the member's allowlist (regressors vs classifiers), frozen action space, direction-
aware primary metric, and budget — no delivery-time-specific path. Out-of-allowlist or
out-of-action-space proposals are rejected before training (bounded agency).

## 5. Export a member to JSON/CSV (DB-free reuse)

```bash
uv run python -m ds_agent_loop.benchmark export wine outputs/benchmark
# writes outputs/benchmark/v1/wine/{descriptor.json,rows.csv,split.json}; round-trips byte-identical
```

## 6. Verify

```bash
uv run pytest tests/test_benchmark.py tests/test_benchmark_persistence.py
```

Covers: descriptor/metric/allowlist validation by task type, stratified-split class preservation,
content-hash stability across loads, version-drift rejection, export round-trip, and
re-materialization idempotency (SC-001…SC-007).

## Acceptance mapping

| SC | Verified by |
|----|-------------|
| SC-001 | load_member byte-identical across two processes |
| SC-002 | suite = 5–6 members, both task types + both provenances, incl. delivery_time |
| SC-003 | content-hash stable; stratified split preserves classes; no leakage |
| SC-004 | loop runs on one regression + one classification member, allowlist/metric correct |
| SC-005 | single version on every member; factor change without bump rejected |
| SC-006 | export round-trips byte-identical; schema via Alembic only |
| SC-007 | re-materialize idempotent; hash divergence fails loudly |
