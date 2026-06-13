# Contract: Benchmark persistence schema (Alembic migration 0002)

New tables added on top of revision `0001`. Schema is created/evolved **exclusively** via Alembic
(`alembic upgrade head` at startup); no operational `create_all` (Principle IV, FR-017).

```
revision = "0002"
down_revision = "0001"
```

## Table `benchmark_members`

| Column | Type | Constraints |
|--------|------|-------------|
| `dataset_id` | String | PK part 1 |
| `benchmark_version` | String | PK part 2 |
| `task_type` | String | not null (`regression`\|`classification`) |
| `provenance` | String | not null (`anchored_synthetic`\|`curated_real`) |
| `target` | String | not null |
| `primary_metric` | String | not null |
| `metric_direction` | Integer | not null (`+1`\|`-1`) |
| `budget` | Integer | not null |
| `patience` | Integer | nullable |
| `feature_schema` | JSONB | |
| `feature_names` | JSONB | |
| `action_space` | JSONB | |
| `model_allowlist` | JSONB | |
| `fingerprint` | String | not null |
| `created_ts` | String | |

PK: `(dataset_id, benchmark_version)`.

## Table `benchmark_splits`

| Column | Type | Constraints |
|--------|------|-------------|
| `dataset_id` | String | PK part 1 |
| `benchmark_version` | String | PK part 2 |
| `train_idx` | JSONB | not null |
| `val_idx` | JSONB | not null |
| `test_idx` | JSONB | not null |
| `content_hash` | String | not null |
| `stratified` | Boolean | not null |
| `n_rows` | Integer | not null |
| `created_ts` | String | |

PK: `(dataset_id, benchmark_version)`.

## upgrade / downgrade

- `upgrade()` — `op.create_table` for both, mirroring `store.py` Table defs (Core).
- `downgrade()` — drop `benchmark_splits` then `benchmark_members`.

## Invariants enforced in code (not DDL)

- Upsert is idempotent on `(dataset_id, benchmark_version)`; an existing row's `content_hash` /
  `fingerprint` MUST equal the recomputed value, else fail loudly (FR-019, FR-014).
- `train_idx ∪ val_idx ∪ test_idx` = `range(n_rows)`, pairwise disjoint; none empty.
