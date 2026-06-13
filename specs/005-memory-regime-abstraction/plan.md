# Implementation Plan: Memory-Regime Abstraction & Decision Provenance

**Branch**: `005-memory-regime-abstraction` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-memory-regime-abstraction/spec.md`

## Summary

Promote the memory seam that 003 shipped provisionally into a **first-class, configuration-selected
abstraction keyed to the 004 benchmark**, and add the **verification layer** that makes the
controlled-variable claim auditable. Most per-decision plumbing already exists: `memory.build_view`
maps `(regime, history, k, latest_artifact)` → a `MemoryView` for all three regimes through a single
seam; `run_cell` persists that exact view (content-hashed) **before** each decision and links it via
`ExperimentRecord.memory_view_ref`; the all-raw context-limit halt, empty-history handling, `k`
clamping, and per-cell JSON/CSV export are all in place.

This feature closes the gaps that turn "memory is the variable" from an assertion into a **verified,
member-keyed, on-demand-checkable** property:

1. **Verified replay (US3/FR-008/009)** — reconstruct any recorded decision's view deterministically
   from persisted history under its recorded regime/`k`/artifact and assert the rebuilt
   `content_hash` equals the stored one, performing no LLM calls; loud mismatch.
2. **Config fingerprint + cross-regime audit (US4/FR-010/011)** — a deterministic digest of every
   held-fixed factor (prompts, action space, allowlist, budget, split, scoring, seed) that
   **excludes** regime/memory, plus an audit that confirms two same-`(member, seed)` cells share a
   fingerprint and differ only in memory — failing loudly on contamination.
3. **Regime-as-config hardening (US1/FR-002/004/012)** — select regime + `k` per single run through
   `Settings`, reject unknowns at startup, resolve the member + frozen split via 004's `load_member`
   (no on-disk fallback in the run path), and reject a regime/`k` change on resume of an existing cell.
4. **On-demand `memory` CLI (FR-017)** — a thin `replay` / `audit` CLI backed by a reusable library,
   mirroring the 004 `benchmark` CLI; verification is never coupled into the loop.

The approach is **harden + verify + re-key**, not a rewrite. `memory.build_view` is unchanged as the
builder seam; one new small module (`provenance.py`) hosts replay/fingerprint/audit and the CLI; the
compacted regime keeps consuming the existing 003 `compaction.py` artifact opaquely. **No new tables
and no Alembic migration** — the fingerprint rides in the existing `ExperimentCell.repro` JSONB and
every view/record is already persisted.

## Technical Context

**Language/Version**: Python ≥ 3.11 (per `pyproject.toml`), run via `uv run`.

**Primary Dependencies**: SQLAlchemy Core + Alembic (existing schema; no migration this feature),
Pydantic v2 / pydantic-settings (typed `MemoryView`/`Settings`), `hashlib` (existing SHA-256 content
hashing), psycopg (Postgres driver). No new top-level dependency.

**Storage**: Single Postgres instance (`DATABASE_URL`); existing `memory_views`, `experiment_records`,
`compaction_artifacts`, `cells` tables suffice. `state/` and JSON/CSV export remain the local mirror.

**Testing**: pytest. Offline unit tests for replay-equivalence, fingerprint determinism/exclusion,
audit pass/fail (via `FakeStore` + in-memory histories); a Postgres-backed integration test reuses
the `test_store_integration.py` pattern (skipped when no DB). Replay/audit make no LLM calls, so they
are fully deterministic and CI-runnable offline.

**Target Platform**: Linux container; `docker compose up` brings up Postgres + `alembic upgrade head`
at startup (unchanged).

**Project Type**: Single `src`-layout research library (`src/ds_agent_loop/`) + thin `entrypoint/`.

**Performance Goals**: Replay/audit are O(iterations) string rebuilds over small histories — seconds
for a whole cell. Reproducibility and determinism dominate; no throughput target.

**Constraints**: Verification MUST add no LLM calls and MUST be deterministic from persisted state
(Principle IX); memory MUST remain the sole manipulated variable per `(member, seed)` (Principle XIII);
failures MUST be loud and specific (Principle X); no new LLM job (FR-016).

**Scale/Scope**: 3 regimes × the 5–6 (member, seed) cells of the 004 suite; one new module + one CLI
entry; no schema change.

## Constitution Check

*GATE: re-checked after design — PASS, no violations.*

- **Principle XIII (Memory as the controlled experimental variable)** — directly satisfied and made
  *verifiable*: one config-selected seam behind three regimes, the exact memory shown persisted per
  decision, and a new audit proving two regimes over a fixed `(member, seed)` differ **only** in
  memory (config fingerprint excludes regime/memory). ✅
- **Principle IX (Reproducible & replayable experiments)** — the new verified-replay path
  reconstructs any decision's view from persisted state with no LLM calls and asserts hash equality;
  a run is provably replayable, not assumed. ✅
- **Principle IV (Inspectable & reproducible, Alembic-managed state)** — no schema change; all views,
  records, and the fingerprint (in `repro` JSONB) persist in Postgres and export to JSON/CSV; no
  ad-hoc DDL, no operational `create_all`. ✅
- **Principle III (Bounded agency) / Principle II (Constrained LLM contracts)** — no new LLM job;
  compacted regime consumes the existing 003 artifact opaquely (FR-016); replay/audit are pure
  deterministic functions. ✅
- **Principle I (Simplicity)** — `memory.build_view` unchanged; exactly one new small module
  (`provenance.py`) for replay/fingerprint/audit + its CLI; everything else extends existing modules. ✅
- **Principles VI/VII/VIII/X** — `uv` toolchain, `notes/` progress snapshot, typed Pydantic models +
  centralized `Settings`, and loud structured logging all already in place and respected. ✅

No entry in Complexity Tracking — there are no justified violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-memory-regime-abstraction/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (replay equivalence, fingerprint, audit, CLI, re-key)
├── data-model.md        # Phase 1 — MemoryView, ConfigFingerprint, ReplayResult, AuditResult
├── quickstart.md        # Phase 1 — run a regime, replay a cell, audit two regimes, export
├── contracts/
│   ├── memory-view.md    # reaffirm/extend the 003 build_view seam contract (member-keyed)
│   └── provenance-api.md # replay_view / verify_cell / config_fingerprint / audit_regimes + CLI
└── checklists/
    └── requirements.md  # already present (passes)
```

### Source Code (repository root)

```text
src/ds_agent_loop/
├── memory.py        # build_view UNCHANGED (the builder seam); docstrings re-key to "member"
├── provenance.py    # NEW: replay_view(), verify_cell(), config_fingerprint(), audit_regimes(),
│                    #   and the thin `memory` CLI (replay / audit) — mirrors benchmark CLI
├── main.py          # EXTEND: single-run path selects regime+k from Settings, resolves member via
│                    #   load_member (no on-disk split fallback in run path), guards regime/k change
│                    #   on resume (FR-012); stamps config fingerprint into cell.repro
├── experiment.py    # EXTEND: stamp config fingerprint into each cell's repro at sweep time
├── prompts.py       # EXTEND: Settings gains a scalar `regime`/`k` for single-run selection (FR-002)
└── store.py         # unchanged (memory_views/records/artifacts/cells already persisted)

tests/
├── test_provenance.py    # NEW: replay byte-identical + hash equality, corrupted-view loud fail,
│                         #   fingerprint determinism/exclusion, audit pass + contamination fail
├── test_memory.py        # EXTEND (or add): regime-as-config selection, unknown rejected,
│                         #   empty-history/k-clamp views replayable
└── test_loop.py          # EXTEND: regime/k change on resume rejected; fingerprint in repro
```

**Structure Decision**: Single research library, extending existing modules plus **one** new
single-purpose module. `memory.py` stays the sanctioned builder seam (unchanged behavior);
`provenance.py` is the matching verifier/auditor and the home of the `memory` CLI — keeping the
build-vs-verify responsibilities cleanly split per Principle I. No new persistence files beyond what
003/004 already created; no Alembic migration.

## Complexity Tracking

No constitution violations — table intentionally empty.
