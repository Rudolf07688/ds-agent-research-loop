# Feature Specification: LLM Autonomous Data Scientist (Toy) Loop

**Feature Branch**: `001-autods-loop`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "The spec is contained in the `notes/` dir - please write it up for us" (source: notes/llm-autods-toy-spec.md)

## Clarifications

### Session 2026-06-13

- Q: On a rejected LLM proposal (out-of-allowlist model, invalid hyperparameters, or
  malformed output), what should the loop do? → A: Skip the rejected proposal, retain
  the current/previous model for that iteration, record the rejection in history, and
  continue the loop.
- Q: How should candidate models be evaluated? → A: k-fold cross-validation (e.g.
  5-fold) with a fixed random seed, reporting mean RMSE as the primary metric.
- Q: Which model is the baseline (the SC-005 reference)? → A: `LinearRegression` —
  the first-iteration baseline that subsequent runs are compared against.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap a seed dataset and reusable data spec (Priority: P1)

A user runs the experiment for the first time with no prior state. The system asks the
LLM once to produce a small realistic sample of delivery records plus a compact,
reusable description of how those records are generated (features, target, rules,
categories, noise level). Both are saved so future runs never need to regenerate them.

**Why this priority**: Nothing else in the loop can happen without an initial dataset
and a reusable generation spec. This is the foundational slice and is independently
valuable: it proves the LLM can bootstrap a usable starting point.

**Independent Test**: Run the experiment in an empty workspace and confirm a seed
sample and a saved data spec are produced and persisted, with no model training
required.

**Acceptance Scenarios**:

1. **Given** no prior saved state, **When** the user starts the experiment, **Then** a
   small seed sample of delivery records and a reusable data spec are generated and
   saved.
2. **Given** a saved seed sample and data spec already exist, **When** the user starts
   the experiment again, **Then** the system reuses them instead of asking the LLM to
   regenerate.
3. **Given** the LLM returns a result, **When** it is received, **Then** it conforms to
   the agreed seed-generation structure (sample records plus a spec containing features,
   target, rules, categories, and noise level).

---

### User Story 2 - Grow the dataset locally without additional LLM calls (Priority: P1)

The user wants a larger dataset for more reliable model evaluation, but without the cost
or distortion of repeatedly asking the LLM. The system expands the dataset locally using
only the originally saved data spec.

**Why this priority**: Cheap, controlled dataset growth is a core promise of the design
and is required before meaningful model comparison. It is independently testable from
the saved spec alone.

**Independent Test**: Starting from a saved data spec, expand the dataset to a larger
target size and confirm the larger dataset is produced with no LLM call and that all
rows follow the saved spec.

**Acceptance Scenarios**:

1. **Given** a saved data spec, **When** the dataset is expanded, **Then** additional
   synthetic rows are produced locally with no LLM call.
2. **Given** repeated expansions across iterations, **When** new rows are generated,
   **Then** they are always derived from the original saved spec, never from a spec that
   was regenerated mid-run.
3. **Given** dataset growth, **When** the dataset size increases, **Then** the cost of
   the run does not scale with dataset size.

---

### User Story 3 - Train, evaluate, and track candidate models (Priority: P1)

On each iteration the system trains one candidate regression model on the current
dataset, scores it with a primary metric, and records the run so progress is auditable
and the best result is preserved.

**Why this priority**: The experiment exists to compare models and learn which performs
best; without training, evaluation, and history the loop produces no value. It is
independently testable given any dataset.

**Independent Test**: Given a dataset and a chosen model, train and score it, then
confirm a new history entry is appended and the best run is updated when the score
improves.

**Acceptance Scenarios**:

1. **Given** a dataset and a selected candidate model, **When** an iteration runs,
   **Then** the model is trained and scored on the primary metric (prediction error).
2. **Given** a completed run, **When** results are recorded, **Then** a history entry
   capturing iteration number, dataset size, model type, hyperparameters, metrics,
   rationale, and timestamp is appended.
3. **Given** a run whose primary metric improves on the prior best, **When** it
   completes, **Then** it is saved as the new best run; otherwise the previous best is
   retained.

---

### User Story 4 - Let the LLM propose the next experiment step (Priority: P2)

After each evaluation, the system shows the LLM the recorded results and asks it to
choose the next action from a fixed set of options (keep the model, tune
hyperparameters, switch model, expand the dataset, or stop), with a short rationale. The
loop applies that decision on the next iteration.

**Why this priority**: This is the "autonomous data scientist" behavior — reasoning over
prior metrics to pick a sensible next step. It depends on history existing (Story 3) but
delivers the headline value of the experiment.

**Independent Test**: Given a populated run history, request a next-step decision and
confirm the returned action is one of the allowed options with a rationale, and that an
invalid or out-of-allowlist proposal is rejected.

**Acceptance Scenarios**:

1. **Given** recorded run results, **When** the LLM is asked for the next step, **Then**
   it returns exactly one action from the allowed set with a rationale.
2. **Given** the LLM proposes a model, **When** the proposal is validated, **Then** only
   models on the approved allowlist are accepted.
3. **Given** the LLM proposes hyperparameters, **When** the proposal is validated,
   **Then** invalid values are rejected before any training occurs.
4. **Given** the LLM proposes anything other than approved configuration (e.g. arbitrary
   code), **When** it is received, **Then** it is rejected and not executed.

---

### User Story 5 - Run the full loop for N iterations with stop conditions (Priority: P2)

The user runs the end-to-end loop: bootstrap (if needed) → expand → train/evaluate → ask
for next step → record → repeat. The loop ends after a fixed number of iterations or
after no improvement for a configured number of consecutive rounds.

**Why this priority**: Ties the slices together into a usable experiment and makes the
run self-terminating. It depends on the earlier stories but is what the user actually
runs.

**Independent Test**: Configure a small iteration count, run the loop end to end, and
confirm it executes each step per iteration and stops at the configured limit or on the
no-improvement condition.

**Acceptance Scenarios**:

1. **Given** a configured iteration count N, **When** the loop runs, **Then** it
   performs the full sequence each iteration and stops after N iterations.
2. **Given** no improvement for the configured number of consecutive rounds, **When**
   that threshold is reached, **Then** the loop stops early.
3. **Given** the loop stops, **When** it finishes, **Then** the recorded history and the
   saved best run reflect all completed iterations.

---

### Edge Cases

- **Partial/invalid LLM output**: The LLM returns output that does not match the agreed
  structure or omits required fields — the run must reject it rather than proceed on
  malformed data.
- **Out-of-allowlist model**: The LLM proposes a model not on the approved list — it
  must be refused without training; the loop skips it, keeps the prior model for that
  iteration, logs the rejection, and continues.
- **Invalid hyperparameters**: Proposed hyperparameters are out of range or wrong type —
  they must be rejected before training; the loop skips the proposal, keeps the prior
  model, logs the rejection, and continues.
- **Resuming mid-experiment**: State files already exist from a prior run — the system
  must resume from those checkpoints rather than regenerating seed data.
- **No improvement at all**: No candidate ever beats the baseline — the best run remains
  the baseline and the loop still terminates cleanly.
- **Empty or corrupt state file**: A required state file exists but is unreadable — the
  run must surface a clear error instead of silently continuing.
- **LLM proposes "stop" immediately**: The first next-step decision is to stop — the loop
  must honor it and end gracefully with valid recorded state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST, on first run with no prior state, obtain from the LLM a small
  seed sample of delivery records and a reusable data spec, and persist both.
- **FR-002**: The reusable data spec MUST capture the features, the target
  (delivery time), generation rules, category definitions, and a noise level.
- **FR-003**: System MUST skip seed/spec generation when valid saved state already
  exists, reusing it instead of calling the LLM again.
- **FR-004**: System MUST expand the dataset to larger sizes locally, deriving all new
  rows solely from the originally saved data spec, with no LLM call during expansion.
- **FR-005**: System MUST NOT regenerate the data spec mid-run; all expansion across
  iterations MUST anchor to the original saved spec.
- **FR-005a**: The first iteration MUST use `LinearRegression` as the baseline model;
  this baseline is the reference point for measuring subsequent improvement.
- **FR-006**: System MUST train exactly one candidate model per iteration on the current
  dataset and score it using k-fold cross-validation (e.g. 5-fold) with a fixed random
  seed, reporting mean RMSE as the primary metric, with optional secondary metrics
  (R², MAE).
- **FR-007**: System MUST restrict model choice to a fixed allowlist of approved
  regressors and reject any model outside that allowlist.
- **FR-008**: System MUST validate all proposed hyperparameters before training and
  reject invalid proposals without training.
- **FR-009**: System MUST treat the LLM as a decision-maker over results only; it MUST
  reject and never execute any LLM-supplied code, accepting only approved configuration.
- **FR-010**: System MUST request a next-step decision from the LLM constrained to a
  fixed set of actions: keep model, tune hyperparameters, switch model, expand dataset,
  or stop — each with a rationale.
- **FR-011**: System MUST append every run to a persistent history record capturing
  iteration number, dataset size, model type, hyperparameters, metrics, rationale, and
  timestamp.
- **FR-012**: System MUST persist the best run separately and update it only when a run's
  primary metric improves on the current best.
- **FR-013**: System MUST run the loop for a configurable number of iterations N and stop
  when N is reached.
- **FR-014**: System MUST stop early when the primary metric has not improved for a
  configured number of consecutive rounds.
- **FR-015**: System MUST keep all durable state in inspectable, human-readable files so
  the experiment can be inspected and rerun from intermediate checkpoints.
- **FR-016**: System MUST reject malformed or incomplete LLM output rather than proceed
  on invalid data.
- **FR-016a**: When a next-step proposal is rejected (out-of-allowlist model, invalid
  hyperparameters, or malformed output), the loop MUST skip that proposal, retain the
  current/previous model for that iteration, record the rejection in history, and
  continue rather than aborting the run.
- **FR-017**: System MUST produce a human-readable summary of the run outcome.
- **FR-018**: I/O-bound operations (notably LLM API calls) MUST use asyncio where it
  provides clear value; CPU-bound model training/evaluation and the intentionally
  sequential loop need not be made async. Async usage MUST NOT add complexity that
  outweighs its benefit for this toy.
- **FR-019**: The design MUST NOT preclude a future deployment as a FastAPI service, but
  building that service (HTTP endpoints, server, request handling) is explicitly OUT OF
  SCOPE for this iteration.

### Key Entities *(include if feature involves data)*

- **Data Spec**: The reusable, LLM-authored description of how delivery records are
  generated — features, target, generation rules, category definitions, and noise level.
  Anchors all local dataset expansion.
- **Seed Sample**: The small initial set of delivery records produced by the LLM to
  bootstrap the dataset.
- **Dataset**: The working collection of delivery records (seed plus locally expanded
  rows) used to train and evaluate models.
- **Run / History Entry**: A record of a single iteration — iteration number, dataset
  size, model type, hyperparameters, metrics, LLM rationale, and timestamp.
- **Best Run**: The single best result observed so far, retained separately from full
  history.
- **Next-Step Decision**: The LLM's constrained choice of the next action (keep, tune,
  switch, expand, or stop), with the proposed model/hyperparameters and a rationale.
- **Model Allowlist**: The fixed set of approved regression models the LLM may choose
  from.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From an empty workspace, the system bootstraps a seed dataset and a saved,
  reusable data spec in a single LLM bootstrap step.
- **SC-002**: The dataset can be grown to a larger target size with zero additional LLM
  calls, and per-run cost does not increase as the dataset grows.
- **SC-003**: A full run of N iterations completes end to end, producing at least N
  recorded history entries (one per iteration) plus a saved best run.
- **SC-004**: 100% of LLM next-step decisions that are accepted fall within the allowed
  action set and the approved model allowlist; any out-of-bounds or malformed proposal
  is rejected and never trains or executes.
- **SC-005**: Across a multi-iteration run, the best recorded primary metric is no worse
  than the `LinearRegression` baseline's metric (the experiment never regresses its
  saved best).
- **SC-006**: After a run, a person can reconstruct what happened — which models were
  tried, with what settings and scores, and why each next step was chosen — from the
  saved state alone, without rerunning.
- **SC-007**: A run can be stopped and restarted from saved state without repeating the
  seed-generation step.

## Assumptions

- This is a single-user, offline, local toy experiment; there is no concurrency,
  multi-user access, UI, database, or production operations/auth concern.
- The prediction task is fixed: estimate delivery time from a small feature set such as
  item count, distance, traffic level, rain indicator, and hour of day.
- Model comparison is limited to a small approved set of regressors (e.g. a linear model
  plus a few tree/boosting ensembles), not an exhaustive search.
- The primary metric is mean RMSE from k-fold cross-validation (fixed seed) for
  interpretability and stable run-to-run comparison; secondary metrics (R^2, MAE) are
  optional.
- Access to an LLM capable of returning structured, schema-constrained output is
  available and configured locally (e.g. via a local environment/credentials file).
- "No improvement for k rounds" and "N iterations" are user-configurable values with
  small sensible defaults.
- The design intentionally excludes multi-agent frameworks, background workers,
  databases, prompt-versioning systems, arbitrary code execution, and production-grade
  observability/auth/retries, consistent with the project constitution.
- asyncio is used where it adds clear value (e.g. awaiting LLM API calls); the toy stays
  a single-process script and does not introduce concurrency frameworks or task queues.
- A future FastAPI deployment is anticipated but out of scope now. The code should remain
  structured so it could later be wrapped in an API (e.g. keeping core logic callable and
  free of CLI-only assumptions), without building any web layer in this iteration.
