# Start Here — 006 (Directional Research Memory compaction operator)

Picks up after `005-memory-regime-abstraction` was implemented and merged. The memory regime is
now the auditable, replayable sole experimental variable; 006 defines the **compaction operator**
that the `compacted_recent` regime consumes.

## What exists now (post-005)

- **Memory regime is pure configuration** behind one `memory.build_view` seam (recent_only /
  all_raw / compacted_recent); select per run via `REGIME` / `--regime`, fail-fast on unknown.
- **Decision provenance is verified**: `provenance.verify_cell` replays every decision's exact
  memory view from persisted history and asserts hash equality (no LLM calls); `audit_regimes`
  proves two cells of one `(member, seed)` differ only in memory via a config fingerprint
  (held-fixed factors, excluding regime/k/memory) stamped in `cell.repro`.
- CLI: `ds-agent-memory replay|audit`. 121 offline tests pass. No 005 schema change/migration.
- The compacted regime currently consumes the **existing 003 `compaction.py`** artifact as an
  **opaque** input (deliberately — 005 did not redefine it).

## What 006 is (roadmap `notes/000-spec-list.md`)

The typed belief-schema compaction artifact — what is **true / failed / unresolved**, and which
**directions** to pursue next — as the **third sanctioned LLM job** (Principle II). Explicit
**outer compaction loop** with recorded cadence; full source→artifact lineage.
*Principles: XII, II, VIII. Thesis ch. 3.*

## Key constraint 005 leaves for 006

006 must be able to **replace the artifact producer without changing the 005 memory seam**:
`memory.build_view` takes the artifact as an opaque dict; keep that contract intact so
verified-replay and the cross-regime audit keep working unchanged.

## Where to look first

- `src/ds_agent_loop/compaction.py` — the existing 003 producer 006 supersedes/hardens.
- `src/ds_agent_loop/memory.py` `build_view` (compacted_recent branch) + `prompts.py`
  (`MemoryView`, `DirectionalMemory`-style artifact shape) — the consumer contract to preserve.
- `store.py` `compaction_artifacts` table + `save_artifact`/`latest_artifact`/`get_artifacts`.
- 005 artifacts for the verification surfaces 006 must not break:
  `specs/005-memory-regime-abstraction/contracts/` (`memory-view.md`, `provenance-api.md`).
- Constitution Principles XII / II / VIII in `.specify/memory/constitution.md`.

## Run / test

```bash
uv sync
uv run pytest                                   # offline suite (121 as of 005)
uv run python -m ds_agent_loop.benchmark materialize   # 004 suite into Postgres (Alembic)
```

## Next command

`/speckit-specify` for **006 — Directional Research Memory Compaction Operator** (then clarify →
plan → tasks → analyze → implement, the same flow used for 004/005).
