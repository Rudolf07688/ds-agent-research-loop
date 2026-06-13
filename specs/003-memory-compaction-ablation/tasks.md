---
description: "Task list for Memory-Compaction Ablation — Directional Research Memory (A/B/C)"
---

# Tasks: Memory-Compaction Ablation — Directional Research Memory (A/B/C)

**Input**: Design documents from `/specs/003-memory-compaction-ablation/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅ (compaction-schema, memory-view, db-schema, runner-cli)

**Tests**: INCLUDED. The spec/plan (constitution Principle XI) explicitly require unit tests for the
deterministic machinery (memory-view construction, compaction parsing, paired stats, export, resume,
splits, scoring). Test tasks below are therefore mandatory, not optional.

**Organization**: Tasks are grouped by user story (US1=P1, US2/US3=P2, US4/US5=P3) so each story can
be implemented and tested independently.

**Baseline**: Feature 002 modules exist (`prompts.py`, `llm.py`, `data_gen.py`, `train.py`,
`history.py`, `main.py`, `entrypoint/`). The 003 ablation modules (`benchmark.py`, `memory.py`,
`compaction.py`, `store.py`, `experiment.py`, `analysis.py`) and the new models/schemas do NOT yet
exist. All file paths below are repository-root relative.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, US3, US4, US5 (Setup/Foundational/Polish carry no story label)

⚠️ **Per CLAUDE.md (constitution v5.1.0)**: before editing any existing symbol (`RunRecord`,
`Settings`, `train.py` scorer, `main.run_loop`, `request_next_step`, `llm._run_structured`,
`entrypoint/run.py`), run GitNexus `impact({target, direction:"upstream"})` first and report the
blast radius; run `detect_changes()` before committing (see T052).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies, settings, and local-infra wiring needed before any module work.

- [ ] T001 Add `sqlalchemy`, `psycopg[binary]`, `scipy`, `matplotlib` to `[project.dependencies]` in `pyproject.toml` and run `uv sync` (research Decisions 1, 9)
- [ ] T002 [P] Add ablation fields (`database_url`, `benchmark_version`, `datasets`, `regimes`, `seeds`, `recent_k`, `compaction_m`, `n_iterations`, `compaction_token_threshold`) with env-var aliases and defaults to the `Settings` class in `src/ds_agent_loop/prompts.py` per `contracts/runner-cli.md`
- [ ] T003 [P] Add `DATABASE_URL` + benchmark/regime/`k`/`m`/seeds knobs (with the Decision-10 defaults) to `.env.example`
- [ ] T004 [P] Update `docker-compose.yml` so the backend service reads `DATABASE_URL`, `depends_on` a healthy `db`, and runs the sweep as its batch command; remove the "app does not yet read from Postgres" note

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Typed models, the Postgres store, the benchmark suite, and the generalized scorer that
ALL user stories depend on.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [ ] T005 Add `MemoryRegime`, `TaskType`, `CellStatus` enums (`CellStatus` includes a terminal `context_limited` value, clarification 2026-06-13); the `MemoryView` and `ExperimentCell` models (`ExperimentCell` carries `last_iteration`); and extend `RunRecord` with `cell_id`, `dataset_id`, `regime`, `seed`, `k`, `m`, `proposal`, `executed_config`, `val_metrics`, `test_metrics`, `improved`, `rejected`, `memory_view_ref`, `runtime_s` in `src/ds_agent_loop/prompts.py` (data-model.md §MemoryView/§ExperimentRecord/§ExperimentCell) — run `impact` on `RunRecord` first
- [ ] T006 [P] Create `src/ds_agent_loop/store.py`: SQLAlchemy Core table defs (`cells`, `experiment_records`, `memory_views`, `compaction_artifacts`, `run_logs`) with a caller-injected `Engine`, plus idempotent `ON CONFLICT (natural_key) DO UPDATE` upserts `upsert_cell` / `append_record` / `save_view` / `save_artifact`, and a JSON-lines stdout + `run_logs` logging sink via `get_logger(cell_id)` per `contracts/db-schema.md` and research Decisions 1–3
- [ ] T007 [P] Create `src/ds_agent_loop/benchmark.py`: `DatasetDescriptor` model + the versioned suite (`delivery_time`, `diabetes`, `california_housing`, `breast_cancer`, `wine`; `adult_income` optional) with offline deterministic loaders, persisted frozen train/val/test split indices reused across all cells, and a `benchmark_version` string (research Decision 4; FR-016/017)
- [ ] T008 [P] Generalize `src/ds_agent_loop/train.py`: add `CLASSIFIER_ALLOWLIST`, replace hard-coded delivery columns + CV with descriptor-driven feature/target handling on the frozen train/val/test split, and metric-aware direction-correct scoring (RMSE↓ / macro-F1↑) — run `impact` on the train/score symbols first (research Decisions 5, 6; FR-018/023)
- [ ] T009 [P] Write `tests/test_store.py`: upsert idempotency and resume-skip behaviour against an in-process fake store / disposable schema (no network) per research Decision 2
- [ ] T010 [P] Write `tests/test_benchmark.py`: splits are frozen and byte-for-byte reproducible across seeds/regimes (SC-002 support)
- [ ] T011 [P] Update `tests/test_train.py`: classifier allowlist selection + fixed-split metric-aware scoring (replaces the delivery-CV assertions)

**Checkpoint**: Models, persistence, benchmark, and scorer ready — user stories can begin.

---

## Phase 3: User Story 1 - Run the loop under a chosen memory strategy (Priority: P1) 🎯 MVP

**Goal**: Run one `(dataset × regime × seed)` cell end-to-end under `recent_only` or `all_raw`, with
a fully logged per-iteration trajectory where the memory slice is the only thing that varies.

**Independent Test**: Run `--dataset delivery_time --regime recent_only --seed 0 --k 5 --iterations 30`,
confirm a per-iteration log recording the exact memory shown (`memory_view_ref`), proposal, executed
config, and val/test metrics; re-run with `--regime all_raw --seed 0` and verify the only difference
is the memory slice (SC-001, SC-002).

### Tests for User Story 1

- [ ] T012 [P] [US1] Write `tests/test_memory.py`: `recent_only` (≤ `k` records) and `all_raw` (full history) views, the fewer-than-`k` early-history edge case (no padding/error), and provenance fields (`included_record_ids`, `rendered_text`, `content_hash`, `prompt_token_count`) per `contracts/memory-view.md`
- [ ] T013 [P] [US1] Write `tests/test_experiment.py` (isolation): assert byte-for-byte equality of all fixed factors (prompt template, schema, model, allowlist, metric, dataset, split, seed, budget) across regimes on a shared `(dataset, seed)`, only `MemoryView` differing (SC-002)

### Implementation for User Story 1

- [ ] T014 [US1] Create `src/ds_agent_loop/memory.py`: `build_view(regime, history, *, k, latest_artifact) -> MemoryView` implementing `recent_only` and `all_raw`, returning rendered text + included ids + `content_hash` + measured `prompt_token_count` (contracts/memory-view.md)
- [ ] T015 [US1] Parameterize the loop into `run_cell(descriptor, regime, seed, *, k, m, iterations)` in `src/ds_agent_loop/main.py` (refactor `run_loop`) — run `impact` on `run_loop` first; calls `memory.build_view`, runs the generalized scorer, builds an `ExperimentRecord` carrying `memory_view_ref`
- [ ] T016 [US1] Wire `store` persistence into `run_cell`: `save_view` BEFORE the agent decides, `append_record` AFTER; record `prompt_token_count` every iteration (growth under `all_raw`, SC-006); no decision recorded without its view (FR-013, Principle XIII). When bounded-agency validation rejects a proposal, preserve the existing `record_rejection` path — set `ExperimentRecord.rejected=true` and emit a rejection `run_logs` event; memory regime MUST NOT alter this behavior (FR-018; spec Edge Cases)
- [ ] T017 [US1] Add lifecycle + per-iteration structured logging in `run_cell` via `get_logger(cell_id)` — memory ids shown, proposal, executed config, val/test metrics, improved flag (FR-013, Principle X)
- [ ] T018 [US1] Add the single-cell CLI to `src/ds_agent_loop/main.py` (`--dataset --regime --seed --k [--m] --iterations`) that creates/resumes the cell and runs it to budget (contracts/runner-cli.md §Single cell)
- [ ] T019 [US1] Handle the `all_raw` context-limit edge case in `run_cell`/`memory.py` (clarification 2026-06-13): on context-window overflow, **stop the cell at that iteration, mark it context-limited, and record the remaining budget as not-run** — emit the event to `run_logs` as H1 evidence, never silently truncate (spec Edge Cases)

**Checkpoint**: A single A or B cell runs end-to-end, fully logged and resumable — MVP deliverable.

---

## Phase 4: User Story 2 - Periodic structured compaction (Condition C) (Priority: P2)

**Goal**: Run `compacted_recent`, generating a `DirectionalMemory` artifact every `m` experiments
(from records at/before the trigger only) and thereafter showing the agent that artifact + last-`k`.

**Independent Test**: Run `--regime compacted_recent --seed 0 --k 5 --m 10 --iterations 30`; confirm
an artifact is generated at each multiple of `m`, validates against the belief schema, is persisted
with `source_record_ids` lineage built only from records ≤ trigger (SC-005), and that the agent then
sees artifact + last-`k` (never full history).

### Tests for User Story 2

- [ ] T020 [P] [US2] Write `tests/test_compaction.py`: trigger fires at every `m`; source records are at/before the trigger only (no future-outcome leakage, SC-005); lineage persisted; malformed/schema-invalid artifact fails fast (FR-010); `compacted_recent` view = artifact + tail-`k` and never the full history (FR-004)

### Implementation for User Story 2

- [ ] T021 [P] [US2] Add the `DirectionalMemory` model, `COMPACTION_SCHEMA`, and `COMPACTION_SYSTEM` prompt to `src/ds_agent_loop/prompts.py` per `contracts/compaction-schema.md` (FR-007, Principle XII)
- [ ] T022 [P] [US2] Add `request_compaction(settings, *, source_records_json, dataset_summary, allowlist) -> DirectionalMemory` to `src/ds_agent_loop/llm.py`, reusing `_run_structured` (third sanctioned structured call); raise `LLMError` on schema failure (FR-010) — run `impact` on `_run_structured` first
- [ ] T023 [US2] Create `src/ds_agent_loop/compaction.py`: outer loop that triggers at cadence `m` over records ≤ trigger; when fewer than `m` source records exist it **compacts over whatever records exist** (deterministic + logged, clarification 2026-06-13), builds the artifact, and persists it with `source_record_ids` lineage via `store.save_artifact`, reused unchanged until the next trigger (FR-006/008/009)
- [ ] T024 [US2] Extend `memory.build_view` for `compacted_recent`: artifact + last-`k` only, and pre-first-trigger behaviour identical to `recent_only` (FR-004; contracts/memory-view.md edge cases)
- [ ] T025 [US2] Integrate compaction into `run_cell` for regime C: invoke `compaction` at triggers, pass `latest_artifact` to `build_view`, persist artifacts; record `compaction` events to `run_logs`
- [ ] T026 [US2] Wire `--m` through the single-cell CLI for `compacted_recent` (contracts/runner-cli.md)

**Checkpoint**: Condition C runs with validated, lineage-stamped artifacts — H2/H3 become testable.

---

## Phase 5: User Story 3 - Full factorial sweep across datasets and seeds (Priority: P2)

**Goal**: One orchestrated run executes every `(dataset × regime × seed)` cell to budget, per-cell
isolated and resumable, aggregated into one inspectable result set in Postgres.

**Independent Test**: Launch the sweep; confirm every cell completes or is recorded `failed` without
aborting siblings (FR-015), all cells share identical fixed factors, and an interrupted+resumed sweep
recomputes no completed cell (SC-003, SC-007).

### Tests for User Story 3

- [ ] T027 [P] [US3] Extend `tests/test_experiment.py` (sweep): factorial enumeration, completed-cell skip on resume (SC-007), one failed cell isolated without aborting others (FR-015), and the exit-code rule (no cell left `running`)

### Implementation for User Story 3

- [ ] T028 [US3] Create `src/ds_agent_loop/experiment.py`: `run_sweep(...)` enumerating dataset × regime × seed, deterministic `cell_id` from the factor tuple, same-baseline start per cell, per-cell try/except → `status=failed,error=...` without aborting siblings, and skip of `status=completed` cells (FR-011/012/015, SC-007)
- [ ] T029 [US3] Add the `experiment sweep` CLI (`--datasets/--regimes/--seeds`) to `src/ds_agent_loop/experiment.py`; exit 0 only if no cell is left `running` (contracts/runner-cli.md §Full sweep)
- [ ] T030 [US3] Update `entrypoint/run.py` to invoke `run_sweep` as the container batch job and surface the sweep exit status — run `impact` on `run.py` first (Principle X)
- [ ] T031 [US3] Finalize `docker-compose.yml`: healthcheck/`depends_on` so the sweep waits for a healthy Postgres and runs to completion with a correct exit code (Principle X; quickstart §3)
- [ ] T032 [US3] Stamp `repro` (commit SHA, settings snapshot, `benchmark_version`, `split_ref`) onto every cell in `experiment.py` (Principle IX)

**Checkpoint**: A full multi-dataset, multi-seed sweep runs, isolates failures, and resumes cleanly.

---

## Phase 6: User Story 4 - Outcome metrics, comparison plots, and significance tests (Priority: P3)

**Goal**: Convert the aggregated result set into primary/secondary outcomes, paired significance
tests with bootstrap CIs, comparison plots, and a human-readable note.

**Independent Test**: Point analysis at a completed export; confirm it emits the primary outcome and
all secondary outcomes per condition, the A-vs-B/B-vs-C/A-vs-C paired tests + bootstrap CIs, the
curves/plots, and a `notes/` summary (SC-004, SC-006, SC-008).

### Tests for User Story 4

- [ ] T033 [P] [US4] Write `tests/test_analysis.py`: primary/secondary outcomes (including the best-so-far **regret curve** `Σ_t (final_best − best_so_far_at_t)`) are metric-direction-aware, and paired tests + bootstrap CIs are deterministic on a fixture export (FR-019/020/021/023)

### Implementation for User Story 4

- [ ] T034 [US4] Add `store.export(out_dir)` + a `store export --out` CLI writing per-cell `records.json` / `memory_views.json` / `artifacts.json` / `logs.csv`, plus `cells.csv` and `outcomes.json` (FR-014a; contracts/db-schema.md §Export)
- [ ] T035 [P] [US4] Add the `OutcomeSummary` and `PairedComparison` models in `src/ds_agent_loop/analysis.py` (data-model.md §OutcomeSummary)
- [ ] T036 [US4] Create `src/ds_agent_loop/analysis.py` outcome computation: primary (best test score under budget) + secondary (best-val-by-iteration, AUC-of-improvement, improving-steps, iters-to-90%, **best-so-far regret curve `Σ_t (final_best − best_so_far_at_t)`** — the regret-style measure of wasted search required by constitution XIV, clarification 2026-06-13, repetition rate, search diversity, prompt-token count), all metric-direction-aware (FR-019/020/023)
- [ ] T037 [US4] Add paired comparisons A-vs-B / B-vs-C / A-vs-C (Wilcoxon signed-rank default, paired-t option) with percentile bootstrap CIs across the per-dataset paired structure in `analysis.py` (FR-021; research Decision 9)
- [ ] T038 [US4] Add matplotlib improvement curves, token-growth curves, and per-dataset paired-difference plots written under `outputs/` in `analysis.py` (FR-022)
- [ ] T039 [US4] Write a human-readable progress/summary note under `notes/` from the analysis output (FR-022, Principle VII)
- [ ] T040 [US4] Add the `analysis --from --out [--threshold-curves]` CLI to `src/ds_agent_loop/analysis.py` (contracts/runner-cli.md §Export & analyze)

**Checkpoint**: The study's findings are regenerable end-to-end from persisted runs.

---

## Phase 7: User Story 5 - Threshold sweep over k and m (Priority: P3 — REQUIRED for DoD)

**Goal**: Vary `k` and `m` over a grid to produce threshold curves locating where raw history begins
to hurt and whether compaction shifts that decline. **Required for DoD** (clarification 2026-06-13):
FR-025 is now a MUST — this is how the study attempts to locate the phase transition obligated by
constitution Principle XIV. (Only the token-threshold trigger, T044/FR-024, remains optional.)

**Independent Test**: Configure a `(k, m)` grid; confirm each combination is a distinct comparable
cell and that performance-vs-`k` / performance-vs-`m` curves are produced from them (FR-025).

### Tests for User Story 5

- [ ] T041 [P] [US5] Extend `tests/test_experiment.py`/`tests/test_analysis.py`: each `(k, m)` combo is a distinct comparable cell and threshold curves are derivable from the recorded grid (FR-025)

### Implementation for User Story 5

- [ ] T042 [US5] Add `--grid-k/--grid-m` to `experiment.py` so the sweep enumerates the `(k, m)` factorial and `cell_id` includes `k` and `m` (FR-025; contracts/runner-cli.md)
- [ ] T043 [US5] Add performance-vs-`k` and performance-vs-`m` threshold curves to `analysis.py` behind `--threshold-curves` (FR-025)
- [ ] T044 [P] [US5] (Optional, SHOULD) Add the token-threshold compaction trigger `t` in `compaction.py` as a secondary mode to fixed cadence (FR-024)

**Checkpoint**: The point estimate is extended to a phase-transition threshold curve.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T045 [P] Update `README.md`: regimes, Directional Research Memory, and the sweep/export/analyze workflow
- [ ] T046 [P] Update `src/ds_agent_loop/__init__.py` to export `run_cell`, `run_sweep`, `Settings`
- [ ] T047 [P] Update `entrypoint/config.py` for any renamed/changed `Settings` fields
- [ ] T048 Run the full offline pytest suite (`uv run pytest`) — confirm hermetic, zero-network, all deterministic machinery covered (Principle XI)
- [ ] T049 [P] Run `quickstart.md` steps 1–5 end-to-end on `delivery_time` and confirm SC-001/002/005/006
- [ ] T050 [P] Add an opt-in Postgres integration test in `tests/test_store_integration.py` exercising real `ON CONFLICT` upserts + resume against the compose `db` (skipped when `DATABASE_URL`/`db` is unavailable, so the offline suite stays hermetic) — resolves research Decision 2 open item / analyze G2
- [ ] T051 Exercise the container path end-to-end: `docker compose up` brings up healthy Postgres, runs a minimal sweep to completion, exits 0, and `run_logs` is populated in Postgres (Principle X; quickstart §3) — the change is "not done" until this passes (constitution Dev-Workflow); resolves analyze G1
- [ ] T052 Run GitNexus `detect_changes({scope:"compare", base_ref:"main"})` and confirm only expected symbols/flows changed before committing (CLAUDE.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **BLOCKS all user stories**.
- **US1 (Phase 3, P1)**: depends on Foundational. The MVP.
- **US2 (Phase 4, P2)**: depends on Foundational + US1's `run_cell`/`memory.py`/`store`.
- **US3 (Phase 5, P2)**: depends on Foundational + US1 `run_cell` (orchestrates cells). Independent of US2 — a sweep can run A/B-only cells.
- **US4 (Phase 6, P3)**: depends on at least one completed cell from US1/US3 (consumes the export).
- **US5 (Phase 7, P3 — REQUIRED for DoD)**: depends on US3 (sweep) + US4 (curves). Mandatory for the Principle-XIV phase-transition obligation; only the optional token-threshold trigger T044 (FR-024) may be dropped. Compaction-`t` (T044) depends on US2.
- **Polish (Phase 8)**: after all targeted stories.

### Within Each User Story

- Tests are written first and expected to fail before implementation.
- Models → store/persistence → orchestration → CLI → edge cases.
- A story is complete and independently testable before the next priority starts.

### Parallel Opportunities

- Setup: T002, T003, T004 in parallel (T001 first — it bootstraps the env).
- Foundational: T006, T007, T008 in parallel after T005 (all import the models); tests T009–T011 in parallel.
- US1 tests T012, T013 in parallel before implementation.
- US2: T021 (prompts) and T022 (llm) in parallel; T023/T024 follow.
- US4: T033 (test) and T035 (models) in parallel; T036→T037→T038→T039 share `analysis.py` (sequential).
- Across teams: once Foundational is done, US1 and the US3 orchestrator scaffolding can proceed in parallel; US4 analysis can be built against a fixture export.

---

## Parallel Example: Foundational Phase

```bash
# After T005 (models in prompts.py) lands, launch the three module builds together:
Task: "Create src/ds_agent_loop/store.py (tables + upserts + logging sink)"   # T006
Task: "Create src/ds_agent_loop/benchmark.py (suite + frozen splits)"          # T007
Task: "Generalize src/ds_agent_loop/train.py (classifiers + fixed-split scoring)" # T008

# And the foundational tests in parallel:
Task: "tests/test_store.py"      # T009
Task: "tests/test_benchmark.py"  # T010
Task: "tests/test_train.py"      # T011
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1.
4. **STOP and VALIDATE**: run one `recent_only` and one `all_raw` cell on `delivery_time`, confirm
   the only difference is the memory slice (SC-001/SC-002) and the trajectory is logged + resumable.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → single-cell A/B study, logged & resumable (MVP).
3. US2 → Condition C with Directional Research Memory (enables H2/H3).
4. US3 → full factorial sweep, isolated failures, resume.
5. US4 → outcomes, paired tests, plots, notes (answers the research questions).
6. US5 → `(k, m)` threshold curves — **required for DoD** (phase-transition localization, Principle XIV); implemented last but not optional.

### Notes

- [P] = different files, no dependency on an incomplete task.
- Commit after each task or logical group; run `detect_changes()` (T052) before committing.
- Tests cover deterministic machinery only; LLM calls are stubbed (zero network), store runs against
  a fake or disposable schema (research Decisions 2, 3).
- Honour the CLAUDE.md GitNexus gate: `impact` before editing `RunRecord`, `Settings`, the `train.py`
  scorer, `run_loop`, `_run_structured`, and `entrypoint/run.py`.
