# Contract: Memory regime → exact memory view (Principle XIII)

The regime is the ONLY manipulated variable. `memory.py` is the single seam that maps a regime +
history (+ latest artifact) to the exact text the agent sees, and records its provenance.

## Interface

```
build_view(
    regime: MemoryRegime,          # recent_only | all_raw | compacted_recent
    history: list[ExperimentRecord],
    *,
    k: int,
    latest_artifact: DirectionalMemory | None,
) -> MemoryView
```

## Per-regime behavior

| regime | included_record_ids | included_artifact_id | invariant |
|--------|---------------------|----------------------|-----------|
| `recent_only` | last `k` raw records | — | never more than `k` records; nothing else from history (FR-002) |
| `all_raw` | every prior raw record | — | full history; `prompt_token_count` grows across iterations (FR-003, SC-006) |
| `compacted_recent` | last `k` raw records | most recent artifact | artifact + tail-`k` only; NEVER the full raw history (FR-004) |

## Provenance (FR-013, Principle XIII)

`build_view` returns a `MemoryView` carrying: `regime`, `included_record_ids`,
`included_artifact_id`, `rendered_text`, `content_hash`, `prompt_token_count`. The caller persists
it (`store.save_view`) **before** the agent decides; the resulting `ExperimentRecord.memory_view_ref`
points at it. No decision may be recorded without its view.

## Fixed-everything-else guarantee (SC-002)

For two cells sharing `(dataset_id, seed)`, the prompt template, output schema, model, allowlist,
primary metric, dataset, split (`split_ref`), seed policy, and budget MUST be identical — only the
`MemoryView` differs. A test asserts byte-for-byte equality of all fixed factors across regimes on a
shared `(dataset, seed)`.

## Edge cases (deterministic + logged)

- Fewer than `k` records early on → show whatever exists, no padding/error.
- `compacted_recent` before the first compaction trigger → behaves identically to `recent_only`.
- all_raw exceeding the model context limit → record the event as an outcome of the condition
  (evidence for H1), never silently truncate (spec Edge Cases; logged via `run_logs`).
