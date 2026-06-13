# Implementation Plan: Directional Research Memory Compaction Operator

**Branch**: `006-directional-research-memory-compaction-operator` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-compaction-operator/spec.md`

## Summary

Promote the compaction operator from the **opaque 003 artifact producer** that 005 consumed into a
**first-class, sanctioned, fully auditable operator** (Principle XII). The mechanism is already
substantially in place from 003: `compaction.py` (`should_compact` / `select_source` /
`compact`) projects the trajectory onto the typed `DirectionalMemory` belief schema as the third
sanctioned LLM job; `main.run_cell` runs the **outer compaction loop** at cadence `m` and persists
each artifact via `store.save_artifact`, which already records `trigger_iteration` and
`source_record_ids` (lineage) under an idempotent `(cell_id, trigger_iteration)` upsert.

This feature closes the gaps that turn "there is a compaction artifact" into a **recorded-cadence,
lineage-complete, audited** operator — mirroring exactly the harden+verify shape 005 used for the
memory seam:

1. **Record the cadence with every artifact (US1/FR-004)** — the explicit cadence `m` (and the
   trigger mode actually used: fixed-cadence vs. compact-over-what-exists) is persisted alongside
   each artifact, not just held in `Settings`. Requires one small additive column.
2. **Lineage audit — no silent signal drop (US2+US3/FR-007/008/009)** — a new **deterministic,
   no-LLM** verifier reconstructs, from persisted history, the exact set of records at or before
   each artifact's trigger and asserts it equals the recorded `source_record_ids`: fails loudly if
   a future record leaked in, if a record at/before the trigger was omitted, or if lineage
   disagrees with history. This is the core new deliverable and the Principle XII "auditable against
   the raw trajectory" enforcement.
3. **Operator hardening (US1/FR-001/002/005/006)** — formalize the operator's invariants as tested
   guarantees: schema-conformance + fail-fast on malformed output, strict no-future-leakage in
   `select_source`, deterministic compact-over-what-exists when the window is short, and a valid
   artifact on a degenerate (all-failed/empty) trajectory.
4. **On-demand `compaction` CLI (US3/FR-014)** — extend the existing `ds-agent-memory` CLI
   (`replay` / `audit`) with a `compaction` subcommand backed by a reusable library function;
   verification is never coupled into the loop.

The approach is **harden + verify + record-cadence**, not a rewrite. `compaction.py` keeps its
producer role; the new verifier lives next to the 005 verifier in `provenance.py` (build-vs-verify
split, Principle I). The **005 memory seam is untouched**: `memory.build_view` keeps consuming the
artifact as an opaque dict, so `provenance.verify_cell` and `provenance.audit_regimes` keep passing
unchanged (FR-011/012). One small additive **Alembic migration 0003** adds the recorded cadence to
`compaction_artifacts` (the only schema change; reversible, like 0001/0002).

## Technical Context

**Language/Version**: Python ≥ 3.11 (per `pyproject.toml`), run via `uv run`.

**Primary Dependencies**: SQLAlchemy Core + Alembic (one additive migration this feature),
Pydantic v2 / pydantic-settings (typed `DirectionalMemory`/`Settings`), `hashlib` (existing SHA-256
content hashing), psycopg (Postgres driver), the existing Vertex/Gemini structured-call path for the
third sanctioned LLM job. No new top-level dependency.

**Storage**: Single Postgres instance (`DATABASE_URL`); existing `compaction_artifacts`,
`experiment_records`, `memory_views`, `cells` tables. Migration **0003** adds a `cadence` column
(and the recorded trigger mode) to `compaction_artifacts`. `state/` + JSON/CSV export remain the
local mirror; `export_cell` already writes `artifacts.json` (extended with cadence).

**Testing**: pytest. Offline unit tests for cadence-triggering, schema/fail-fast, no-future-leakage,
compact-over-what-exists, degenerate-trajectory, lineage completeness, and audit pass/tamper (via
`FakeStore` + in-memory histories with an injected hermetic `request_fn`/`compactor`); a
Postgres-backed integration test reuses `test_store_integration.py` and validates the migration
(upgrade → downgrade → upgrade). The lineage audit makes **no LLM calls** and is fully deterministic.

**Target Platform**: Linux container; `docker compose up` brings up Postgres + `alembic upgrade head`
at startup (now lands on 0003).

**Project Type**: Single `src`-layout research library (`src/ds_agent_loop/`) + thin `entrypoint/`.

**Performance Goals**: Compaction is one bounded LLM call per trigger (≤ iterations/`m` per cell).
The lineage audit is O(artifacts × records) set comparison over small histories — sub-second per
cell. Reproducibility and determinism dominate; no throughput target.

**Constraints**: Compaction MUST remain the only third sanctioned LLM job and emit schema-validated
JSON, failing fast on malformed output (Principles II, XII); it MUST see only records at/before the
trigger (no future leakage, Principle XII); the lineage audit MUST add no LLM calls and be
deterministic from persisted state (Principle IX); the 005 memory seam, replay, and cross-regime
audit MUST remain byte-for-byte unchanged (FR-011/012/013); failures MUST be loud and specific
(Principle X).

**Scale/Scope**: 1 operator + 1 outer loop (existing) hardened; 1 new verifier function + 1 CLI
subcommand; 1 additive migration; the `compacted_recent` regime over the 5–6 `(member, seed)` cells
of the 004 suite.

## Constitution Check

*GATE: re-checked after design — PASS, no violations.*

- **Principle XII (Directional Research Memory)** — directly and centrally satisfied: the artifact
  is the typed `DirectionalMemory` belief schema (TRUE/FAILED/UNRESOLVED/DIRECTIONS), produced by an
  explicit **outer** loop on a **recorded** cadence, with **full source→artifact lineage** persisted
  and a new audit proving it cannot **silently drop signal** that can't be checked against the raw
  trajectory. ✅
- **Principle II (Constrained LLM contracts)** — compaction stays the only third sanctioned LLM job,
  emitting schema-validated structured JSON via Pydantic; malformed output fails fast; no new LLM
  job is introduced (the verifier is pure/deterministic). ✅
- **Principle VIII (Typed models & centralized Settings)** — the belief schema is a Pydantic model
  with `extra="forbid"`; the cadence is a centralized `Settings.compaction_m` field surfaced into
  recorded lineage; new verifier results are typed models. ✅
- **Principle IV (Inspectable & reproducible, Alembic-managed state)** — the single schema change is
  an **additive, reversible** Alembic migration (0003); lineage + cadence persist in Postgres and
  export to JSON; no ad-hoc DDL, no operational `create_all`. ✅
- **Principle IX (Reproducible & replayable)** — the lineage audit reconstructs each artifact's
  source set from persisted history with no LLM calls and asserts equality; faithful production is
  provable, not assumed. ✅
- **Principle XIII (Memory as the controlled variable)** — preserved untouched: `build_view` keeps
  the opaque-dict contract, the other two regimes and the regime-selection/decision-provenance
  contracts are unchanged, and 005 verified-replay + cross-regime audit keep passing. ✅
- **Principles I / VI / VII / X** — producer left in place and verifier placed beside the 005
  verifier (no new module needed); `uv` toolchain; `notes/` snapshot updated; loud structured
  logging on every trigger and audit failure. ✅

No entry in Complexity Tracking — there are no justified violations.

## Project Structure

### Documentation (this feature)

```text
specs/006-compaction-operator/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (cadence recording & migration, lineage audit,
│                        #   operator hardening, CLI surface, seam-unchanged guarantee)
├── data-model.md        # Phase 1 — DirectionalMemory (restated), artifact lineage + cadence,
│                        #   CompactionAuditResult, migration 0003 delta
├── quickstart.md        # Phase 1 — run compacted_recent, inspect lineage, audit a cell, confirm
│                        #   005 replay/audit still pass
├── contracts/
│   ├── compaction-operator.md  # the operator + outer-loop + lineage contract (producer side)
│   └── lineage-audit-api.md     # verify_artifact_lineage / audit_compaction + `compaction` CLI
└── checklists/
    └── requirements.md  # already present (passes)
```

### Source Code (repository root)

```text
src/ds_agent_loop/
├── compaction.py    # HARDEN: should_compact/select_source/compact invariants made explicit &
│                    #   tested; emit the trigger mode actually used (fixed vs compact-over-what-exists)
├── main.py          # EXTEND: outer compaction loop passes cadence (and trigger mode) into
│                    #   save_artifact so it is recorded with the artifact (FR-004)
├── store.py         # EXTEND: compaction_artifacts gains `cadence` (+ trigger mode); save_artifact
│                    #   records it; get_artifacts/latest_artifact/export carry it through
├── provenance.py    # EXTEND: verify_artifact_lineage() / audit_compaction() (no-LLM, deterministic)
│                    #   + `ds-agent-memory compaction` CLI subcommand — beside the 005 verifier
├── prompts.py       # MINIMAL: typed CompactionAuditResult / lineage models; Settings unchanged
│                    #   (compaction_m already exists)
└── (memory.py UNCHANGED — the 005 opaque-dict seam is preserved verbatim)

alembic/versions/
└── 0003_compaction_cadence.py   # NEW: additive `cadence` (+ trigger mode) on compaction_artifacts;
                                 #   reversible (upgrade → downgrade → upgrade verified)

tests/
├── test_compaction.py    # NEW/EXTEND: cadence trigger points, no-future-leakage in select_source,
│                         #   schema fail-fast on malformed output, compact-over-what-exists,
│                         #   degenerate-trajectory valid artifact
├── test_provenance.py    # EXTEND: lineage audit pass; tamper (future record / omitted record /
│                         #   lineage-history disagreement) fails loudly with artifact+iteration
└── test_loop.py          # EXTEND: cadence recorded on each artifact; 005 replay/audit unchanged
                          #   for a compacted_recent cell backed by the operator
```

**Structure Decision**: Single research library. The producer (`compaction.py`) keeps its role and
is hardened in place; the matching verifier/auditor goes into the **existing** `provenance.py`
beside the 005 replay/audit code, keeping build-vs-verify cleanly split (Principle I) and reusing
the established `ds-agent-memory` CLI surface. `memory.py` is untouched so the 005 seam and its
guarantees are preserved. The only persistence change is the additive migration 0003.

## Complexity Tracking

No constitution violations — table intentionally empty.
