# Feature Specification: Benchmark Harness & Dataset Suite

**Feature Branch**: `004-benchmark-harness`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "whats the next spec that we need to define and implement? See `notes/000-spec-list.md` and git logs" — resolved to roadmap entry **004 — Benchmark Harness & Dataset Suite** (`notes/000-spec-list.md`), the dependency-sketch unblocker for features 005–010.

## Overview

This feature builds the **fixed, versioned benchmark** that every downstream study depends on:
a small suite of tabular datasets — spanning **both regression and classification** — each with a
**frozen train/validation/test split**, a **pre-registered primary metric** (and optimization
direction), a **fixed per-dataset experiment budget**, a **frozen action space**, and a
**task-appropriate model allowlist** (regressors for regression members, classifiers for
classification members). The suite is published under a single **benchmark version**, so any result
produced later can name the exact benchmark it ran against.

The suite mixes two provenance kinds: **anchored-synthetic** datasets (each expanded
deterministically in Python from a saved `data_spec`, with no further LLM calls — the seed
delivery-time regression task is one such member) and a small set of **curated real public tabular
datasets** bundled with the project for external validity. For every member, the frozen split rows
are **materialized and persisted in Postgres** (managed by Alembic migrations) and are
**exportable to human-readable JSON/CSV**, so the split is byte-identical across every regime and
seed and is fully inspectable.

This feature deliberately scopes to the **data and harness layer only**. It does **not** introduce
the memory regimes (feature 005), the Directional Research Memory compaction operator (006), or the
A/B/C ablation study (007). Its job is to make the existing autonomous-data-scientist loop runnable
against **any suite member by id** under that member's fixed factors, and to make the whole suite
versioned, persisted, and inspectable — so that later features change only memory while everything
data-related is already held constant.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define and materialize a single versioned benchmark member (Priority: P1)

As a researcher, I can declare one benchmark dataset — its id, task type, feature/target schema,
data source (anchored-synthetic spec or curated real dataset), a frozen train/validation/test
split, a pre-registered primary metric with direction, a fixed experiment budget, a frozen action
space, and a task-appropriate model allowlist — and materialize it once so that loading it by id
later returns byte-identical data and the exact same fixed factors.

**Why this priority**: This is the irreducible unit of the benchmark. Without one fully specified,
reproducibly loadable member, there is no suite and nothing downstream can run fairly. A single
member is itself valuable: it lets the existing loop run against a precisely-pinned task.

**Independent Test**: Declare one member (e.g. the seed delivery-time regression task), materialize
it, then load it by id twice (in separate processes) and confirm the returned train/val/test rows,
the split assignment, the primary metric and direction, the budget, the action space, and the
allowlist are byte-for-byte identical both times.

**Acceptance Scenarios**:

1. **Given** a declared member with an anchored synthetic `data_spec` and a fixed seed, **When** it
   is materialized, **Then** its rows are generated in Python with no LLM calls and the resulting
   train/validation/test split is persisted and stamped with a content hash.
2. **Given** a materialized member, **When** it is loaded by id in two separate runs, **Then** the
   split rows, split assignment, primary metric (with direction), budget, action space, and model
   allowlist are identical across both loads.
3. **Given** a member declared as classification, **When** it is materialized, **Then** its model
   allowlist contains only classifiers and its primary metric is a classification metric
   (higher-is-better); a regression member analogously yields only regressors and a
   lower-is-better metric.

---

### User Story 2 - A mixed regression+classification suite (Priority: P2)

As a researcher, I can assemble the declared members into one **suite** of 4–6 datasets that spans
both regression and classification and both provenance kinds (anchored-synthetic and curated real
public datasets), with the seed delivery-time task as one member, and enumerate the whole suite
programmatically.

**Why this priority**: The thesis needs diversity across task types and data provenance to make
paired comparisons meaningful; a single member (US1) proves the mechanism but cannot support a
benchmark. It depends on US1's per-member definition being correct.

**Independent Test**: Materialize the full suite; enumerate it; confirm it contains 4–6 members,
includes at least one regression and at least one classification dataset, includes at least one
anchored-synthetic and at least one curated-real member, and that each member is individually
loadable per US1 with its own fixed factors.

**Acceptance Scenarios**:

1. **Given** the suite definition, **When** it is materialized, **Then** every member is persisted
   with its split, metric, budget, action space, and allowlist, and the suite enumerates exactly
   the declared members.
2. **Given** the assembled suite, **When** it is inspected, **Then** it contains both regression and
   classification members and both anchored-synthetic and curated-real members, and the seed
   delivery-time task appears as one member.
3. **Given** a curated-real member, **When** it is materialized, **Then** its source rows come from
   the bundled public dataset (no network access required at run time) and are split and persisted
   identically to a synthetic member.

---

### User Story 3 - Versioned benchmark with recorded changes (Priority: P2)

As a researcher, I can refer to the suite by a single **benchmark version**, and any change to a
dataset, split, action space, allowlist, budget, or metric is a recorded versioned change, so that
every result produced downstream names the exact benchmark version it was produced against.

**Why this priority**: Fair comparison across regimes and seeds (the whole point of the study)
requires the data, splits, and budgets to be provably constant. Versioning is what lets a result
cite an immutable benchmark and lets a reviewer re-derive it. It depends on the suite (US2)
existing.

**Independent Test**: Read the benchmark version from a materialized suite; change a single member's
split policy; confirm the change is rejected unless accompanied by a recorded version bump, and that
the new version is distinguishable from the old so prior results remain attributable to the old
version.

**Acceptance Scenarios**:

1. **Given** a materialized suite, **When** its version is queried, **Then** a single benchmark
   version identifier is returned and is attached to every member.
2. **Given** an attempt to alter a member's split, action space, allowlist, budget, or metric,
   **When** it is made without a recorded version change, **Then** it is rejected (drift is not
   silently absorbed).
3. **Given** a recorded version bump, **When** the suite is re-materialized, **Then** the new
   version coexists with the prior one for attribution and the change is recorded with what changed.

---

### User Story 4 - Run the existing loop against any suite member by id (Priority: P2)

As a researcher, I can run the existing autonomous-data-scientist loop against **any** suite member
by passing its id, and the loop trains/evaluates only models from that member's allowlist, takes
only actions from that member's frozen action space, scores against that member's primary metric,
and stops at that member's fixed budget — with the seed delivery-time task no longer special-cased.

**Why this priority**: The benchmark is only useful if the loop can actually run on every member
under that member's fixed factors. This generalizes the loop off the single delivery-time dataset
(the re-plan goal) and is the bridge to features 005–007. It depends on US1–US3.

**Independent Test**: Run the loop against a classification member and against a regression member
by id; confirm each run uses the correct allowlist (classifiers vs regressors), enforces the frozen
action space, scores with the member's primary metric in the correct direction, and terminates at
the member's budget — with no delivery-time-specific assumptions in the path.

**Acceptance Scenarios**:

1. **Given** a regression member id, **When** the loop runs, **Then** it proposes and trains only
   allowlisted regressors, scores with the member's lower-is-better metric, and stops at the
   member's budget.
2. **Given** a classification member id, **When** the loop runs, **Then** it proposes and trains
   only allowlisted classifiers, scores with the member's higher-is-better metric, and an
   out-of-allowlist or out-of-action-space proposal is rejected before training (bounded agency).
3. **Given** any member id, **When** the loop runs, **Then** it uses that member's frozen split with
   no leakage of test rows into training and no delivery-time-specific code path.

---

### User Story 5 - Inspect and export the persisted benchmark (Priority: P3)

As a researcher, I can inspect the persisted benchmark — its members, splits, action spaces,
allowlists, budgets, metrics, and version — directly in Postgres, and export any member (including
its materialized split rows) to human-readable JSON/CSV, so the benchmark is debuggable and
reusable without database access.

**Why this priority**: Inspectability and export are constitutional requirements (Principle IV) and
make the benchmark trustworthy and portable, but they consume the persisted artifacts of US1–US3, so
they come last.

**Independent Test**: Point the export at a materialized suite; confirm it writes per-member
descriptors and split rows to JSON/CSV that round-trip back to byte-identical data, and that the
documented Postgres schema (created via an Alembic migration) matches what was persisted.

**Acceptance Scenarios**:

1. **Given** a materialized suite, **When** export runs, **Then** each member's descriptor and its
   train/validation/test rows are written as JSON/CSV that reload to byte-identical data.
2. **Given** the benchmark schema, **When** it is inspected, **Then** it is documented and was
   created/evolved exclusively through Alembic migrations (no ad-hoc DDL or operational
   `create_all`).
3. **Given** the persisted suite, **When** queried, **Then** members, splits, fixed factors, and the
   benchmark version are all retrievable for downstream attribution.

---

### Edge Cases

- **Synthetic spec drift**: if an anchored synthetic member is re-materialized, the generated rows
  MUST match the previously persisted split (verified by content hash); a mismatch MUST fail loudly
  rather than silently replacing data.
- **Curated-real dataset availability**: curated real datasets MUST be bundled/vendored so
  materialization needs no network access at run time; a missing bundled dataset MUST fail fast with
  a clear error.
- **Class imbalance / tiny classes**: for classification members, the frozen split MUST be stratified
  where a class would otherwise be absent from a split; a member whose split cannot preserve all
  classes MUST be flagged at materialization, not at run time.
- **Metric/task-type mismatch**: declaring a classification metric for a regression member (or a
  regressor allowlist for a classification member) MUST be rejected at declaration time.
- **Budget exhaustion vs no-improvement stop**: each member declares both a hard iteration budget
  `N` and an optional no-improvement patience `k`; the loop stops at whichever the member
  pre-registers, and the stop reason MUST be recorded.
- **Re-materialization idempotency**: materializing an already-materialized suite version MUST be
  idempotent — it neither duplicates nor corrupts persisted members.
- **Version attribution**: a result that names an old benchmark version MUST remain re-derivable
  even after a newer version exists.
- **Empty or degenerate split request**: a split policy that would leave a partition empty (e.g.
  test fraction 0, or a dataset smaller than the requested split) MUST be rejected at declaration.

## Requirements *(mandatory)*

### Functional Requirements

**Dataset members & schema**

- **FR-001**: The system MUST represent each benchmark member with a typed descriptor capturing: a
  stable id, task type (regression | classification), provenance kind (anchored-synthetic |
  curated-real), feature/target schema, the frozen split, the primary metric and its optimization
  direction, the fixed experiment budget, the frozen action space, and the task-appropriate model
  allowlist.
- **FR-002**: Anchored-synthetic members MUST be expanded deterministically in Python from a saved
  `data_spec` with no LLM calls, and token usage MUST NOT scale with dataset size (growth happens in
  Python only).
- **FR-003**: Curated-real members MUST be sourced from public tabular datasets bundled/vendored
  with the project so materialization requires no network access at run time.
- **FR-004**: Each member MUST declare exactly one pre-registered primary metric with an explicit
  optimization direction (e.g. RMSE/lower-is-better for regression, accuracy or macro-F1 /
  higher-is-better for classification); secondary metrics MAY be declared but MUST be explicit.

**Suite composition**

- **FR-005**: The system MUST assemble members into one suite of 4–6 datasets that includes at least
  one regression and at least one classification member, and at least one anchored-synthetic and at
  least one curated-real member.
- **FR-006**: The seed delivery-time regression task MUST appear as one member of the suite (one
  member, not the whole project), and MAY serve as the development/smoke dataset.
- **FR-007**: The suite MUST be enumerable programmatically, and every member MUST be individually
  loadable by id.

**Frozen splits**

- **FR-008**: Each member MUST have one fixed train/validation/test split that is materialized and
  persisted, identical across every later regime and seed.
- **FR-009**: The materialized split rows MUST be persisted in Postgres and stamped with a content
  hash, so byte-identical reuse is verifiable; classification splits MUST be stratified to preserve
  all classes across partitions.
- **FR-010**: Loading a member MUST never leak test rows into training/validation; the split
  assignment is fixed at materialization, not re-drawn at load.

**Action space & allowlist (bounded agency)**

- **FR-011**: Each member MUST carry a frozen action space (the enumerated next-step actions) that is
  identical across all future runs of that member.
- **FR-012**: Each member MUST carry a fixed, versioned model allowlist of a handful of scikit-learn
  estimators — regressors only for regression members, classifiers only for classification members —
  and proposals outside the allowlist or action space MUST be rejected before training, never
  silently coerced.

**Versioning**

- **FR-013**: The suite MUST publish a single benchmark version identifier attached to every member,
  so any downstream result can name the exact benchmark version it ran against.
- **FR-014**: Any change to a member's dataset, split, action space, allowlist, budget, or metric
  MUST be a recorded versioned change; uncoordinated drift MUST be rejected, and prior versions MUST
  remain attributable so old results stay re-derivable.

**Loop generalization**

- **FR-015**: The existing autonomous-data-scientist loop MUST run against any suite member by id,
  using that member's split, primary metric (direction-aware), action space, allowlist, and budget,
  with no delivery-time-specific code path.
- **FR-016**: The loop MUST terminate per the member's pre-registered stop condition (hard budget
  `N`, or no improvement for `k` rounds where declared) and MUST record the stop reason.

**Persistence, inspectability & export**

- **FR-017**: All benchmark state (member descriptors, splits/rows, action spaces, allowlists,
  budgets, metrics, version) MUST be persisted in a single Postgres instance whose schema is
  documented and managed exclusively through Alembic migrations (no ad-hoc DDL or operational
  `create_all`).
- **FR-018**: Any member, including its materialized split rows and its full descriptor, MUST be
  exportable to human-readable JSON/CSV that round-trips back to byte-identical data, so the
  benchmark is usable and inspectable without database access.
- **FR-019**: Re-materializing an already-materialized benchmark version MUST be idempotent —
  neither duplicating nor corrupting persisted members — and a synthetic re-materialization whose
  generated rows do not match the persisted content hash MUST fail loudly.

### Key Entities *(include if feature involves data)*

- **Benchmark suite**: the versioned collection of members published under one benchmark version;
  the unit a downstream study cites.
- **Dataset member (descriptor)**: one task — id, task type, provenance kind, feature/target schema,
  frozen split reference, primary metric + direction, fixed budget, frozen action space, and model
  allowlist.
- **Data spec**: for anchored-synthetic members, the saved specification from which rows are
  deterministically generated in Python (no LLM calls).
- **Frozen split**: the fixed assignment of rows to train/validation/test for a member, materialized
  and content-hashed, identical across all regimes and seeds.
- **Action space**: the enumerated set of next-step actions available to the agent for a member,
  held fixed across runs.
- **Model allowlist**: the fixed, versioned set of scikit-learn estimators permitted for a member —
  regressors for regression members, classifiers for classification members.
- **Benchmark version**: the identifier stamping the whole suite; changes to any fixed factor
  require a recorded version change, and old versions remain attributable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can declare, materialize, and load any single benchmark member by id and
  obtain byte-identical data and fixed factors (split, metric+direction, budget, action space,
  allowlist) across separate loads.
- **SC-002**: The materialized suite contains 4–6 members spanning both regression and
  classification and both anchored-synthetic and curated-real provenance, with the seed
  delivery-time task as one member.
- **SC-003**: Every member's train/validation/test split is frozen, content-hashed, and verifiably
  identical across reloads, with no test-row leakage and (for classification) all classes preserved
  across partitions.
- **SC-004**: The existing loop runs to completion against at least one regression member and one
  classification member, using the correct (direction-aware) metric and the task-appropriate
  allowlist, with out-of-allowlist/out-of-action-space proposals rejected before training and with
  no delivery-time-specific code path.
- **SC-005**: The suite reports a single benchmark version attached to every member, and an attempt
  to change any fixed factor without a recorded version bump is rejected.
- **SC-006**: Any member, including its split rows, exports to JSON/CSV that reloads to byte-identical
  data, and the Postgres schema backing the benchmark is documented and was created solely via
  Alembic migrations.
- **SC-007**: Re-materializing an existing benchmark version is idempotent (no duplication or
  corruption), and a synthetic re-materialization that diverges from the persisted content hash
  fails loudly rather than silently overwriting.

## Assumptions

- **Datasets are synthetic-anchored + curated-real, small/moderate.** Per the chosen scope, the
  suite mixes deterministically-generated synthetic members (anchored to a saved `data_spec`, no LLM
  calls) and a small set of bundled public tabular datasets (e.g. scikit-learn's built-in datasets
  such as diabetes/california-housing for regression and wine/breast-cancer for classification).
  Datasets are small/moderate so a later full multi-regime, multi-seed sweep is feasible offline on
  a single machine.
- **Initial suite size is 4–6 members, mixed task types.** Roughly balanced between regression and
  classification, expandable in later benchmark versions; exact membership is finalized in planning.
- **Frozen splits are materialized in Postgres.** The exact split rows (plus a content hash) are
  persisted in Postgres and exportable to JSON/CSV, guaranteeing byte-identical reuse across regimes
  and seeds and easy inspection; the seed single-run path MAY still mirror core state to `state/`
  files for cheap local debugging (Principle IV).
- **Schema is owned by Alembic.** Benchmark tables are defined with SQLAlchemy Core and the schema is
  created/evolved exclusively through Alembic migrations applied with `alembic upgrade head`
  (constitution Principle IV, v5.2.0); `create_all` is restricted to ephemeral/test use.
- **The loop is generalized, not rewritten.** The existing inner loop, training/scoring, history
  handling, prompts/schemas, and centralized settings are extended to take a dataset member by id
  and its fixed factors; the per-iteration agent contract and the bounded-agency rules are unchanged.
  Memory regimes, the Directional Research Memory compaction operator, and the A/B/C study are **out
  of scope** here and land in features 005, 006, and 007 respectively.
- **LLM backend is the current Vertex AI / Gemini + minimal ADK setup** (feature 002); this feature
  adds no new LLM job — dataset generation stays anchored/Python-side and the proposal contract is
  unchanged.
- **Reproducibility is seed-policy bounded.** Split selection and training are deterministic under
  the fixed seed policy; irreducible LLM proposal non-determinism is handled later by running
  multiple seeds (feature 007), not by this feature.

## Dependencies

- Builds on feature **002** (Vertex AI / Gemini + minimal ADK backend, containerization) and the
  Postgres + Alembic persistence established around feature 003 (commits `130ef01`, `190537b`).
- Reuses and generalizes existing modules: the experiment loop, training/scoring, history logging,
  prompts/schemas, the data-generation path, and centralized settings — extended, not replaced
  (see `src/ds_agent_loop/`, e.g. `data_gen.py`, `train.py`, `benchmark.py`, `store.py`).
- **Postgres** (single instance, e.g. `postgres:17-alpine`) for durable benchmark persistence,
  orchestrated for local runs by the root `docker-compose.yml` and reached via `DATABASE_URL`;
  schema changes ship as **Alembic** migrations.
- **Unblocks** features **005** (memory-regime abstraction), **006** (compaction operator), **007**
  (A/B/C ablation study), and downstream **008–010** — none of which can fairly compare regimes
  without this fixed, versioned benchmark (per the roadmap dependency sketch).
- The project **constitution** (v5.2.0) governs: Principle V (fixed, versioned benchmark datasets),
  Principle III (bounded agency / fixed allowlist widened to classifiers), and Principle IV
  (inspectable, reproducible, Alembic-managed state) are the primary constraints this feature
  satisfies. Thesis chapter 4.
