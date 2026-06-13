# Phase 1 Data Model: Memory-Regime Abstraction & Decision Provenance

This feature adds **no new persisted tables**. It reuses the 003/004 schema and introduces two small
in-memory result models plus one derived field stamped into existing JSONB. Entities below are marked
**(existing)**, **(new model)**, or **(derived)**.

## MemoryView *(existing — `prompts.MemoryView`, table `memory_views`)*

The exact memory slice shown to the agent at one decision. Unchanged by this feature except that its
key is now understood as `(member, seed, regime, iteration)` via `cell_id`.

| Field | Type | Notes |
|-------|------|-------|
| `cell_id` | str | encodes member/dataset id, regime, seed, k, m |
| `iteration` | int | per-cell decision index (stable id, also lineage key) |
| `regime` | MemoryRegime | recent_only \| all_raw \| compacted_recent |
| `included_record_ids` | list[int] | ordered iterations included (≤ `k`, or all for all_raw) |
| `included_artifact_id` | str \| None | compacted regime only |
| `rendered_text` | str | the exact text shown to the agent |
| `content_hash` | str | SHA-256 of `rendered_text`; the equality token |
| `prompt_token_count` | int | deterministic ~4-char/token proxy (all-raw overflow guard) |

**Invariants**: persisted **before** the decision; `ExperimentRecord.memory_view_ref == content_hash`;
unique `(cell_id, iteration)`.

## ConfigFingerprint *(derived — stamped into `ExperimentCell.repro["config_fingerprint"]`)*

A stable digest of every held-fixed factor, **excluding** regime, `k`, and memory content. The
equality token for the cross-regime audit.

| Input factor | Source | In fingerprint? |
|--------------|--------|-----------------|
| prompt/schema version | `prompts` (fixed templates) | ✅ |
| action space | `descriptor.action_space` | ✅ |
| model allowlist | `allowlist_for(task_type)` | ✅ |
| budget `N` | `descriptor.budget` / iterations | ✅ |
| patience | `descriptor.patience` | ✅ |
| split + benchmark version | `descriptor.split_ref`, `benchmark_version` | ✅ |
| scoring | `descriptor.primary_metric` + `metric_direction` | ✅ |
| seed | cell `seed` | ✅ |
| **regime** | cell `regime` | ❌ excluded (the intervention) |
| **k** (memory tail) | cell `k` | ❌ excluded (memory config) |
| **memory content** | `MemoryView.*` | ❌ excluded |

**Computation**: SHA-256 over a canonical JSON dump (sorted keys, normalized scalars). Deterministic
and order-independent. No schema change — `repro` is already `JSONB`.

## ReplayResult *(new model — in-memory, `provenance.py`)*

The outcome of verifying a cell's decisions are replayable.

| Field | Type | Notes |
|-------|------|-------|
| `cell_id` | str | the cell verified |
| `total` | int | decisions checked |
| `matched` | int | rebuilt hash == stored hash |
| `ok` | bool | `matched == total` |
| `mismatches` | list[ReplayMismatch] | each: `iteration`, `expected_hash`, `actual_hash` |

**Invariant**: replay performs **no LLM calls** and reads only persisted state. `ok == False` MUST
surface every mismatching iteration loudly (Principle X).

## AuditResult *(new model — in-memory, `provenance.py`)*

The outcome of auditing two cells as a memory-only comparison.

| Field | Type | Notes |
|-------|------|-------|
| `cell_a` / `cell_b` | str | the two cells compared |
| `same_member_seed` | bool | gate: must be True to be a valid comparison |
| `fingerprint_equal` | bool | held-fixed factors identical |
| `differing_factor` | str \| None | first contaminating factor when `fingerprint_equal` is False |
| `differing_dimension` | str | the intended difference, e.g. `regime: recent_only → all_raw` |
| `ok` | bool | `same_member_seed and fingerprint_equal` |
| `view_pairs` | list[tuple[MemoryView, MemoryView]] | per-iteration views for side-by-side inspection |

**Invariants**: a pair with differing `(member, seed)` yields `ok=False` with reason "not a
memory-only comparison"; a held-fixed-factor difference yields `ok=False` naming `differing_factor`.

## ExperimentRecord *(existing — `prompts.RunRecord`)*

Unchanged. Continues to reference the producing view via `memory_view_ref` (== `MemoryView.content_hash`).

## ExperimentCell *(existing — `prompts.ExperimentCell`)*

Unchanged shape. `repro` (JSONB) gains the derived `config_fingerprint` key (Decision 2). One regime
and one `k` for the cell's lifetime (FR-012) — a resume with mismatched regime/`k` is rejected.

## Memory regime *(existing — `prompts.MemoryRegime` enum)*

`recent_only | all_raw | compacted_recent`. Now also selectable as a scalar `Settings.regime` for the
single-run path, validated against the enum at startup (unknown → fail-fast, FR-002).
