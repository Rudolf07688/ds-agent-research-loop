# Contract: Postgres schema + JSON/CSV export (Principles IV, IX, X)

Single Postgres instance via `DATABASE_URL`. Tables defined once in `store.py` (SQLAlchemy Core).
Postgres is an ADDITION to inspectable state: everything exports to human-readable JSON/CSV
(FR-014a). All upserts are idempotent on the natural key so resume neither duplicates nor corrupts.

## Tables

```
cells(
  cell_id PK, dataset_id, regime, seed, k, m, budget,
  status, error, repro JSONB, created_ts, updated_ts
)                                            -- one per (dataset×regime×seed×k×m); FR-014

experiment_records(
  id PK, cell_id FK, iteration, dataset_id, regime, seed, k, m,
  proposal JSONB, executed_config JSONB, val_metrics JSONB, test_metrics JSONB,
  improved, rejected, memory_view_ref FK, model_name, hyperparameters JSONB,
  runtime_s, rationale, timestamp,
  UNIQUE(cell_id, iteration)                 -- idempotent per iteration; FR-013
)

memory_views(
  content_hash PK, cell_id FK, iteration, regime,
  included_record_ids JSONB, included_artifact_id, rendered_text,
  prompt_token_count,
  UNIQUE(cell_id, iteration)                 -- exact memory shown; Principle XIII / FR-013
)

compaction_artifacts(
  artifact_id PK, cell_id FK, trigger_iteration,
  artifact JSONB,                            -- the DirectionalMemory belief schema
  source_record_ids JSONB,                   -- lineage; FR-009 / SC-005
  created_ts,
  UNIQUE(cell_id, trigger_iteration)
)

run_logs(
  id PK, cell_id, iteration, level, event, payload JSONB, ts
)                                            -- structured logging; Principle X
```

## Resume / idempotency (FR-014, SC-007, Principle IX/X)

- `upsert_cell` / `append_record` / `save_view` / `save_artifact` use
  `INSERT ... ON CONFLICT (natural_key) DO UPDATE` so a re-run of an in-flight cell is safe.
- The orchestrator skips any cell whose `status = completed` (no recompute, no new LLM calls).
- A cell that errors sets `status=failed, error=...` and does NOT abort sibling cells (FR-015).

## Export (FR-014a, Principle IV)

`store.export(out_dir)` writes, per cell:
- `outputs/export/<cell_id>/records.json`, `memory_views.json`, `artifacts.json`, `logs.csv`
- `outputs/export/cells.csv` (index of all cells + status)
- `outputs/export/outcomes.json` (analysis summaries)

so the entire experiment is debuggable and rerunnable-in-analysis without database access. The
schema (this file) is the documented mapping required by Principle IV.
