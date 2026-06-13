# Contract: Compaction operator + outer loop + lineage (producer side)

The compaction operator is the **only third sanctioned LLM job** (Principle II) and the central
object of study (Principle XII). 006 hardens the existing 003 producer and records its cadence; the
belief schema and the consumer seam are unchanged.

## Operator (existing — `compaction.py`, hardened & pinned by tests)

```
should_compact(iteration, m, *, prompt_tokens=None, token_threshold=None) -> bool
    # fires at every m-th iteration (fixed cadence), or when prompt_tokens > token_threshold

select_source(history, trigger_iteration) -> list[ExperimentRecord]
    # MUST return ONLY records with iteration <= trigger_iteration  (no future-outcome leakage)
    # fewer than m present -> returns whatever exists (compact-over-what-exists)

async compact(settings, *, source_records, descriptor, request_fn=None) -> dict
    # projects source_records onto the DirectionalMemory belief schema; structured JSON only.
    # malformed / non-conforming output -> raises LLMError (fail fast). Returns artifact as a dict.
```

**Invariants guaranteed (tested, SC-001/002/003/006):**
- No future leakage: every source record has `iteration <= trigger_iteration`.
- Schema conformance: output validates against `COMPACTION_SCHEMA` / `DirectionalMemory`
  (`extra="forbid"`, `0 ≤ confidence ≤ 1`); otherwise fail fast — never persist a malformed artifact.
- Compact-over-what-exists: short window compacts whatever exists, deterministically, recording
  `trigger_mode = compact_over_what_exists`.
- Degenerate trajectory: still yields a valid artifact.

## Outer compaction loop (existing — `main.run_cell`, extended to record cadence)

```
# once per inner iteration i, for regime == compacted_recent and a wired compactor:
if compaction.should_compact(i, m, ...):
    source        = compaction.select_source(history_records, i)   # at/before trigger only
    artifact_dict = await compactor(settings, source_records=source, descriptor=descriptor)
    store.save_artifact(
        cell_id=cid, trigger_iteration=i, artifact=artifact_dict,
        source_record_ids=[r.id for r in source],
        cadence=m, trigger_mode=mode,           # <-- NEW (FR-004/006): cadence recorded with artifact
    )
    latest_artifact = store.latest_artifact(cid)
    log.info("compaction_done", iteration=i, source_records=len(source), cadence=m, mode=mode)
```

- The cadence `m` is `Settings.compaction_m`, explicit and now **recorded with every artifact**.
- Idempotent: re-running a trigger replaces the `(cell_id, trigger_iteration)` row (FR-010).

## Consumer seam (UNCHANGED — 005 contract, restated)

`memory.build_view(regime, history, *, k, latest_artifact, ...)` continues to receive the artifact
as an **opaque dict** and render it via `_render_artifact`. 006 changes **nothing** here:

- `build_view` signature, behavior, and `MemoryView` output are byte-for-byte unchanged (FR-011).
- `provenance.verify_cell` and `provenance.audit_regimes` (005) keep passing for a
  `compacted_recent` cell backed by the operator (FR-012, SC-005).
- The recent-only / all-raw regimes, regime selection, and decision provenance are untouched (FR-013).
