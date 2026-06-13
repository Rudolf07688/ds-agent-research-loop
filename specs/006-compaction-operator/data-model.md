# Phase 1 Data Model: Directional Research Memory Compaction Operator

Restates the operator's existing types and defines the **new lineage/audit surface** plus the
migration 0003 delta. Existing 003/005 models are shown for context; only the **bold/NEW** parts are
introduced by 006.

## DirectionalMemory (existing — Principle XII belief schema, restated)

The typed artifact the operator produces. `extra="forbid"`. Unchanged by 006.

| Field | Type | Rule |
|-------|------|------|
| `confirmed_findings` | `list[str]` | what is probably TRUE |
| `failed_directions` | `list[str]` | what has likely FAILED |
| `promising_directions` | `list[str]` | broad DIRECTIONS to pursue next |
| `best_known_configs` | `list[BestKnownConfig]` | `{model_name, hyperparameters, metric}` |
| `unresolved_questions` | `list[str]` | what remains UNRESOLVED |
| `next_step_recommendation` | `str` | single recommendation |
| `confidence` | `float` | `0 ≤ x ≤ 1` |
| `rationale` | `str` | short justification |

A degenerate trajectory still yields a *valid* artifact (e.g. empty lists + an
`unresolved_questions` entry) — never a malformed one (FR-002, edge case).

## Compaction artifact row + lineage (existing columns + **NEW**)

Persisted in `compaction_artifacts`. One row per `(cell_id, trigger_iteration)` (idempotent upsert).

| Column | Type | Source | Rule |
|--------|------|--------|------|
| `artifact_id` | `str` PK | existing | `"{cell_id}@{trigger_iteration}"` |
| `cell_id` | `str` | existing | owning cell |
| `trigger_iteration` | `int` | existing | the outer-loop trigger point |
| `artifact` | JSONB | existing | the `DirectionalMemory` dump |
| `source_record_ids` | JSONB | existing | identities of the exact source records summarized |
| `created_ts` | `str` | existing | creation timestamp |
| **`cadence`** | **`int`** | **NEW (0003)** | **the explicit `m` in effect at this trigger (FR-004)** |
| **`trigger_mode`** | **`str`** | **NEW (0003)** | **`fixed` \| `compact_over_what_exists` (FR-006)** |

**Lineage invariant (audited, FR-005/007/008):** `set(source_record_ids)` MUST equal
`{ r.id for r in history if r.iteration <= trigger_iteration }` as reconstructed from persisted
history. No id with `iteration > trigger_iteration` may appear (no future leakage).

## CompactionAuditResult (**NEW** — typed, `provenance.py`/`prompts.py`)

Result of the deterministic, no-LLM lineage audit over one cell.

| Field | Type | Meaning |
|-------|------|---------|
| `cell_id` | `str` | audited cell |
| `artifacts_checked` | `int` | number of artifacts audited |
| `ok` | `bool` | all artifacts respect their lineage |
| `llm_calls` | `int` | MUST be `0` (asserted) |
| `mismatches` | `list[LineageMismatch]` | empty iff `ok` |

### LineageMismatch (**NEW**)

| Field | Type | Meaning |
|-------|------|---------|
| `artifact_id` | `str` | offending artifact |
| `trigger_iteration` | `int` | its trigger |
| `kind` | `str` | `future_record_leaked` \| `record_omitted` \| `history_disagreement` |
| `record_id` | `int \| None` | the offending source record, when applicable |
| `detail` | `str` | human-readable explanation |

## Settings (existing — unchanged)

`compaction_m: int = 10` (cadence), `compaction_token_threshold: int | None`, plus the 005
`regime` / `recent_k`. 006 surfaces `compaction_m` into the recorded artifact lineage; it adds **no**
new Settings field.

## Migration 0003 delta

- **Up**: `ALTER TABLE compaction_artifacts ADD COLUMN cadence INTEGER` and
  `ADD COLUMN trigger_mode VARCHAR`. Additive, nullable (existing rows read back `NULL`, treated as
  "cadence unrecorded — pre-006"). `FakeStore` mirror updated in lockstep.
- **Down**: drop both columns. Reversible; verified upgrade → downgrade → upgrade and idempotent,
  matching the 0002 acceptance bar.

## Relationships

```
ExperimentCell (cell_id)
  └─1:N─ compaction_artifacts (cell_id, trigger_iteration)   ← cadence, trigger_mode, source_record_ids
            └─ source_record_ids ──references──> experiment_records.id  (iteration <= trigger_iteration)
  └─1:N─ experiment_records ── memory_view_ref ──> memory_views   (005 seam, UNCHANGED)
```
