# Phase 1 Data Model: Memory-Compaction Ablation

**Feature**: `003-memory-compaction-ablation` | **Gate**: constitution v5.0.0 (Principles VIII, XII–XIV)

All entities are Pydantic models (Principle VIII), persisted to Postgres (Principle IV) and
exportable to JSON/CSV (FR-014a). New models live in `prompts.py` (alongside the existing typed
entities) unless noted.

## DirectionalMemory  *(the compaction artifact — Principle XII)*

The structured projection of the raw trajectory onto stable beliefs. Produced by the third
sanctioned LLM call; validated against `COMPACTION_SCHEMA`.

| field | type | notes |
|-------|------|-------|
| `confirmed_findings` | `list[str]` | what is probably TRUE |
| `failed_directions` | `list[str]` | what has likely FAILED |
| `promising_directions` | `list[str]` | DIRECTIONS worth pursuing next |
| `best_known_configs` | `list[dict]` | best (model, hyperparameters, metric) seen so far |
| `unresolved_questions` | `list[str]` | what remains UNRESOLVED |
| `next_step_recommendation` | `str` | the directional nudge for the inner loop |
| `confidence` | `float` (0–1) | self-reported confidence |
| `rationale` | `str` | short justification |

**Provenance (not LLM-authored, attached on persist):** `artifact_id`, `cell_id`, `trigger_iteration`,
`source_record_ids` (lineage — which experiments it summarized; FR-009), `created_ts`.
**Rule:** built only from records at/before `trigger_iteration` (no future leakage, FR-008/SC-005);
reused unchanged until the next trigger.

## MemoryView  *(what the agent actually saw — Principle XIII)*

The exact memory slice presented at one iteration. Persisted per decision so every decision is
replayable and regimes are auditable against each other (FR-013).

| field | type | notes |
|-------|------|-------|
| `cell_id` | `str` | owning cell |
| `iteration` | `int` | decision point |
| `regime` | `MemoryRegime` enum | `recent_only` \| `all_raw` \| `compacted_recent` |
| `included_record_ids` | `list[int]` | raw records shown (≤ `k`, all, or tail-`k`) |
| `included_artifact_id` | `str \| None` | the DirectionalMemory shown (regime C only) |
| `rendered_text` | `str` | exact prompt-memory text the agent received |
| `content_hash` | `str` | hash of `rendered_text` for cheap equality/audit |
| `prompt_token_count` | `int` | measured (SC-006) |

`MemoryRegime` is a new `str, Enum`. `memory.build_view(...)` is the only constructor.

## ExperimentRecord  *(extends the existing `RunRecord`)*

One iteration's full result — the atomic unit of history and logging (FR-013). Existing fields
(`iteration`, `model_name`, `hyperparameters`, `metrics`, `rationale`, `timestamp`) plus:

| added field | type | notes |
|-------|------|-------|
| `cell_id` | `str` | owning cell |
| `dataset_id` | `str` | suite member |
| `regime` | `MemoryRegime` | active regime |
| `seed` | `int` | cell seed |
| `k` / `m` | `int` | window / cadence in effect |
| `proposal` | `NextStepDecision` | the agent's raw proposal |
| `executed_config` | `dict` | what actually ran after validation |
| `val_metrics` / `test_metrics` | `dict[str,float]` | split-aware (Decision 6) |
| `improved` | `bool` | beat the incumbent on the primary metric |
| `rejected` | `bool` | bounded-agency rejection (proposal not executed) |
| `memory_view_ref` | `str` | FK → `MemoryView.content_hash` |
| `runtime_s` | `float` | wall-clock for the iteration |

## DatasetDescriptor  *(benchmark member — Principle V)*

Defined in `benchmark.py`; the suite is `list[DatasetDescriptor]` + a `benchmark_version`.

| field | type | notes |
|-------|------|-------|
| `dataset_id` | `str` | stable id |
| `task_type` | `TaskType` enum | `regression` \| `classification` |
| `feature_schema` | `dict` | column → {numeric \| categorical} |
| `target` | `str` | target column |
| `primary_metric` | `str` | e.g. `rmse`, `macro_f1` |
| `metric_direction` | `+1/-1` | higher- vs lower-is-better (FR-023) |
| `split_ref` | `str` | id of the frozen train/val/test index split (FR-017) |
| `loader` | callable | offline, deterministic (research Decision 4) |

## ExperimentCell  *(one sweep unit — Principles IX, XIII; FR-014)*

One `(dataset × regime × seed [× k × m])` unit; owns its budget, trajectory, status, resume state.

| field | type | notes |
|-------|------|-------|
| `cell_id` | `str` | deterministic from the factor tuple (idempotent key) |
| `dataset_id`,`regime`,`seed`,`k`,`m` | factors | the manipulated + fixed factors |
| `budget` | `int` | iterations (`N`) |
| `status` | `CellStatus` enum | `pending` \| `running` \| `completed` \| `failed` |
| `error` | `str \| None` | recorded on failure without aborting siblings (FR-015) |
| `repro` | `dict` | commit, settings snapshot, benchmark_version, split_ref (Principle IX) |
| `created_ts`/`updated_ts` | `str` | lifecycle |

**Resume rule:** a `completed` cell is never recomputed (SC-007); upserts keyed by `cell_id`.

## OutcomeSummary  *(analysis output — Principle XIV; FR-019–021)*

Per-cell and per-condition aggregates plus paired comparisons.

| field | type | notes |
|-------|------|-------|
| `primary_outcome` | `float` | best test score under budget |
| `secondary` | `dict` | AUC-improvement, improving-steps, iters-to-90%, repetition-rate, search-diversity, token-growth |
| `comparisons` | `list[PairedComparison]` | A-vs-B, B-vs-C, A-vs-C: effect, CI, p-value |
| `threshold_curves` | `dict` | performance vs `k`, vs `m` (US5/FR-025) |

## Relationships

```
Benchmark(version) ──< DatasetDescriptor ──< ExperimentCell ──< ExperimentRecord
                                                   │                  │
                                                   │                  └─ memory_view_ref ─> MemoryView
                                                   └──< DirectionalMemory (regime C) ──source_record_ids──> ExperimentRecord
ExperimentCell ──< run_logs (structured logging, Principle X)
OutcomeSummary  ── derived-from ──> ExperimentRecord (regenerable, Principle XI)
```

## Validation & invariants

- Memory regime is the ONLY field that changes the agent's visible context across cells sharing a
  `(dataset, seed)` (SC-002); all other factors identical.
- DirectionalMemory MUST validate against `COMPACTION_SCHEMA` or the cell fails fast (FR-010).
- Every `ExperimentRecord.memory_view_ref` MUST resolve to a stored `MemoryView` (no decision
  without recorded provenance, Principle XIII).
- Every persisted entity MUST round-trip to JSON/CSV export (FR-014a).
