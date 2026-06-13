# Quickstart: Directional Research Memory Compaction Operator

Prereqs: `uv sync`; Postgres up (`docker compose up` runs `alembic upgrade head`, now landing on
migration **0003**).

## 1. Run a `compacted_recent` cell (operator + outer loop at recorded cadence)

```bash
# regime is pure config (005); the outer compaction loop fires at cadence m and records it.
REGIME=compacted_recent \
uv run python -m ds_agent_loop.main --member delivery_time --seed 0 --k 3 --m 5 --iterations 20
```

At every 5th iteration a `DirectionalMemory` artifact is produced from the records at/before that
iteration and persisted with its `source_record_ids`, **`cadence=5`**, and `trigger_mode`.

## 2. Inspect lineage + audit a cell (on demand, no LLM calls)

```bash
ds-agent-memory compaction <cell_id>
# Per artifact: trigger_iteration, cadence, trigger_mode, source-record count
# Verdict:      OK (n artifacts, 0 LLM calls)   — or each LineageMismatch + non-zero exit
```

This proves every artifact summarized exactly the records at/before its trigger — no future
leakage, nothing silently dropped (Principle XII, FR-007/008/009).

## 3. Confirm the 005 guarantees still hold (seam unchanged)

```bash
ds-agent-memory replay <cell_id>     # every decision's memory view still replays to its hash
ds-agent-memory audit <cell_id_a> <cell_id_b>   # two regimes still differ ONLY in memory
```

Both pass unchanged because `memory.build_view` keeps consuming the artifact as an opaque dict
(FR-011/012, SC-005).

## 4. Run the offline suite

```bash
uv run pytest        # adds: cadence triggering, schema fail-fast, no-future-leakage,
                     # compact-over-what-exists, degenerate trajectory, lineage completeness,
                     # audit pass/tamper, migration up/down, 005 replay/audit unchanged
```

## What success looks like (maps to Success Criteria)

- Artifacts appear at exactly the cadence triggers, all schema-conforming (SC-001), malformed output
  rejected (SC-002).
- A tampered source set (future record / omitted record) is caught by the audit (SC-003).
- Every artifact's lineage resolves cell + trigger + cadence + source ids; audit makes 0 LLM calls
  (SC-004).
- 005 replay + cross-regime audit pass unchanged (SC-005); re-running a trigger yields one artifact
  (SC-006); suite stays green and grows (SC-007).
