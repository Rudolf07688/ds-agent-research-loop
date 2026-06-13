# Contract: Lineage audit API + `ds-agent-memory compaction` CLI

New verifier in `provenance.py`, beside the 005 `verify_cell` / `audit_regimes`. Pure,
deterministic, **no LLM calls** (Principle IX). Reads persisted state via the `store` interface
(real `Store` or `FakeStore`). Enforces the Principle XII guarantee that the operator cannot
silently drop signal that can't be audited against the raw trajectory.

## Library API

```python
def verify_artifact_lineage(
    artifact_row: dict,                  # one compaction_artifacts row (incl. source_record_ids, trigger_iteration)
    history: list[ExperimentRecord],     # the cell's full persisted history
) -> LineageMismatch | None:
    # Reconstruct expected = { r.id for r in history if r.iteration <= artifact_row["trigger_iteration"] }
    # Compare to set(artifact_row["source_record_ids"]):
    #   - any recorded id with iteration > trigger      -> LineageMismatch(kind="future_record_leaked")
    #   - any expected id missing from recorded         -> LineageMismatch(kind="record_omitted")
    #   - recorded id absent from history               -> LineageMismatch(kind="history_disagreement")
    # Returns None when lineage is exact.


def audit_compaction(store, cell_id: str) -> CompactionAuditResult:
    # Loads every artifact (get_artifacts) + history for the cell, runs verify_artifact_lineage on
    # each, performs ZERO LLM calls, and aggregates. ok == (mismatches == []). Artifacts are checked
    # in trigger-iteration order; the result records artifacts_checked and llm_calls (== 0).
```

### Guarantees

- **No LLM calls** — `CompactionAuditResult.llm_calls == 0`, asserted (Principle IX, SC-004).
- **Loud + specific** — each mismatch names `artifact_id`, `trigger_iteration`, `kind`, the offending
  `record_id`, and a `detail` string (Principle X, FR-009).
- **Coverage** — a passing audit reports `artifacts_checked` and the verified source coverage
  (SC-003/004).
- **Idempotent input** — duplicate `(cell_id, trigger_iteration)` cannot occur (store upsert), so
  each trigger is audited once.

## CLI (FR-014) — extends `ds-agent-memory`

```
ds-agent-memory compaction <cell_id>
```

- Prints, per artifact: `trigger_iteration`, `cadence`, `trigger_mode`, source-record count.
- Prints the audit verdict: `OK (n artifacts, 0 LLM calls)` or each `LineageMismatch` with a
  non-zero exit code on failure.
- Backed entirely by `audit_compaction`; never invoked inside the run loop (on demand only),
  mirroring the existing `replay` / `audit` subcommands.

## Out of scope

- Semantic judging of *which beliefs* were kept/dropped (would require an LLM judge — forbidden as a
  fourth job; deferred to trajectory analysis in feature 008).
- Any change to `memory.build_view`, the 005 replay/cross-regime audit, or the other two regimes.
