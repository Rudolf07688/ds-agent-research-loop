<!--
SYNC IMPACT REPORT
==================
Version change: 3.0.0 → 4.0.0
Bump rationale: MAJOR — the project is formally re-scoped from a "toy" experiment to a rigorous,
  REPLAYABLE RESEARCH PROJECT whose deliverable is a research / whitepaper document. This relaxes a
  binding Principle I non-goal ("no production-grade observability/retries"): comprehensive
  structured logging and a flawless containerized entrypoint are now REQUIRED, not excluded — a
  backward-incompatible governance change (mirrors the v2.0.0 ADK and v3.0.0 Postgres relaxations).
  Three new principles are added: IX Reproducible & Replayable Experiments, X Operational
  Reliability & Observability, XI Research Rigor & Whitepaper Outcome. Principle I is amended to
  retain simplicity-of-design as an anti-over-engineering guard while SUBORDINATING it to the
  reproducibility, reliability, and observability the research goal demands. Safety principles II
  (structured JSON only) and III (bounded agency, no code execution) are UNCHANGED and remain the
  non-negotiable boundaries.

Principles:
  I.    Simplicity & Readability First            (amended — simplicity serves, never overrides, rigor)
  II.   Constrained LLM Contracts (Structured JSON Only)  (unchanged)
  III.  Bounded Agency (No Arbitrary Code Execution)      (unchanged)
  IV.   Inspectable & Reproducible State          (unchanged since v3.0.0)
  V.    Anchored Synthetic Data Generation        (unchanged)
  VI.   uv-Managed Python Environment             (unchanged)
  VII.  Progress Communicated via notes/          (unchanged)
  VIII. Typed Models & Centralized Settings (Pydantic)   (unchanged)
  IX.   Reproducible & Replayable Experiments     (NEW)
  X.    Operational Reliability & Observability    (NEW)
  XI.   Research Rigor & Whitepaper Outcome        (NEW)

Added sections: Principles IX, X, XI
Removed sections: none

Templates / docs requiring review:
  ✅ .specify/memory/constitution.md (this file)
  ✅ .specify/templates/plan-template.md (generic Constitution Check gate — no change)
  ✅ .specify/templates/spec-template.md (no mandatory-section change)
  ✅ .specify/templates/tasks-template.md (generic categories cover logging/repro tasks — no change)
  ⚠ specs/003-memory-compaction-ablation/spec.md (already requires Postgres persistence + per-cell
     provenance; add explicit structured-logging/observability, flawless-entrypoint, and replay
     acceptance criteria to fully satisfy Principles IX–XI when planning)
  ⚠ docker-compose.yml + Dockerfile + entrypoint/ (the entrypoint MUST run flawlessly with
     structured logging emitting to / retrievable from Postgres — verify against Principle X)
  ⚠ README.md / .env.example (document the logging + Postgres emit/retrieve + replay workflow when
     feature 003 is implemented)

Deferred TODOs:
  - README.md + .env.example logging / Postgres / replay wiring — deferred to feature 003
    implementation, not part of this governance amendment.
-->

# LLM Autonomous Data Scientist (Research) Constitution

## Core Principles

### I. Simplicity & Readability First

The repository MUST prefer readability and short, single-purpose files over needless abstraction.
This is a rigorous, replayable RESEARCH project — not a toy, and not a multi-tenant production
platform. Simplicity-of-design is retained as an anti-over-engineering guard, but it is
SUBORDINATE to the reproducibility, reliability, and observability the research goal demands
(Principles IX–XI): the code stays small and hackable, while the experiment around it is
engineered to research standards.

- The library is a small `src`-layout package (`src/ds_agent_loop/`) of single-purpose
  modules (`llm.py`, `data_gen.py`, `train.py`, `history.py`, `prompts.py`, `main.py`).
  This single-purpose-module decomposition MUST be preserved. (Earlier revisions kept these
  modules at the repo root; packaging them under `src/` for publishing is permitted and does
  not change the decomposition.)
- A SINGLE, MINIMAL agent framework — Google's Agent Development Kit (ADK) — is permitted,
  used ONLY to host the two sanctioned LLM calls of Principle II. Its use MUST stay minimal:
  no additional tools, no autonomous actions, no multi-step planning or self-directed control
  flow beyond the fixed seed → next-step pattern. The ADK agent is bound by Principles II and
  III at all times. (This is a deliberate, bounded exception to the otherwise standing ban on
  frameworks; prior revisions prohibited agent frameworks outright.)
- Beyond that one permitted ADK agent, new indirection layers, additional agent frameworks,
  multi-agent systems, or general orchestration engines remain prohibited.
- Only a thin deployment consumer (`entrypoint/`) and runtime artifact directories
  (`state/`, `outputs/`, `notes/`, `entrypoint/runs/`) live outside the package. The
  consumer imports FROM the library, never the reverse; library logic MUST NOT leak into
  `entrypoint/`.
- YAGNI applies: features are added only when the experiment loop concretely needs
  them. Speculative generality MUST be justified before introduction.
- Non-goals are binding: no multi-agent frameworks or orchestration beyond the single minimal
  ADK agent above, no web/GUI front-end, no authentication / multi-tenant concerns, no
  prompt-versioning systems, and no always-on background services beyond the batch experiment
  entrypoint. A SINGLE Postgres instance is permitted, but ONLY as a durable persistence backend
  for experiment / memory-compaction state under Principle IV; general-purpose or additional
  database use beyond that one purpose remains out of scope.
- AMENDED (v4.0.0): comprehensive structured logging, a flawless containerized entrypoint, and
  bounded, logged retries where they aid reliable replay are NO LONGER excluded — they are
  REQUIRED by Principles IX and X. The earlier blanket exclusion of "production-grade
  observability/retries" is lifted; what remains out of scope is operational sprawl that does not
  serve reproducibility (auth, UIs, microservices, autoscaling, and the like).

Rationale: The repo stays hackable and inspectable, but it now underwrites a research result, so
gratuitous complexity is still rejected while reproducibility, reliability, and observability are
actively required. ADK is admitted only because the chosen backend (Gemini on Vertex AI) is most
naturally driven through it; admitting it minimally — fenced in by the structured-output and
bounded-agency principles — keeps the system inspectable while honoring the required technology.

### II. Constrained LLM Contracts (Structured JSON Only)

Every LLM interaction MUST use a developer-supplied JSON schema. Exactly two schemas
are sanctioned: the seed-generation schema and the next-step schema.

- The LLM has exactly two jobs: (a) generate the seed dataset plus a compact reusable
  `data_spec`, and (b) propose the next experiment step by reasoning over recorded
  metrics. It MUST NOT take on additional responsibilities. The permitted ADK agent
  (Principle I) MUST NOT expand this to a third job or any open-ended tool use.
- Free-form parsing of LLM output is prohibited; outputs MUST be schema-constrained
  structured JSON.
- The next-step `action` MUST be one of the enumerated values
  (`keep_model | tune_hyperparameters | switch_model | expand_dataset | stop`).

Rationale: Schema-constrained output keeps the LLM's role narrow and interpretable
and removes parser brittleness.

### III. Bounded Agency (No Arbitrary Code Execution)

The LLM reasons over results; it MUST NOT execute or emit code that the system runs.

- The LLM MAY select models only from a fixed allowlist of scikit-learn regressors
  (`LinearRegression`, `RandomForestRegressor`, `GradientBoostingRegressor`, and
  optionally `HistGradientBoostingRegressor`).
- The LLM MAY suggest only JSON configuration, never raw Python to be executed.
- Python MUST validate all proposed hyperparameters before training; invalid or
  out-of-allowlist proposals MUST be rejected, not silently coerced into execution.
- The permitted ADK agent MUST NOT be given tools, function-calling, or code-execution
  capabilities that would let the model take actions beyond emitting the two sanctioned
  structured proposals. Any agent "tools" are limited to the deterministic, developer-written
  steps of the fixed loop.

Rationale: This prevents the repo from degrading into an uncontrolled agent sandbox
and keeps every action auditable.

### IV. Inspectable & Reproducible State

The experiment MUST be inspectable at every step and rerunnable from intermediate
checkpoints.

- Core experiment state lives as plain files under `state/` (`data_spec.json`,
  `seed_rows.json`, `dataset.csv`, `history.json`, `best_run.json`); human-readable
  formats are required.
- Every run MUST be appended to `state/history.json` recording at minimum: iteration
  number, dataset size, model type, hyperparameters, metrics, LLM rationale, and
  timestamp.
- The best run MUST be persisted separately (`best_run.json`). A new run is accepted
  only when the primary metric (RMSE) improves.
- Seed/spec generation MUST be skipped when prior state already exists, so the loop
  can resume from checkpoints without redundant LLM calls.
- A SINGLE Postgres instance MAY additionally persist the larger-scale ablation harness's
  state (e.g. per-cell trajectories, compaction artifacts and their source lineage) for
  feature 003. It is an ADDITION, not a replacement: the database schema MUST be documented
  and its contents MUST remain inspectable and exportable to the same human-readable JSON/CSV
  forms, so the experiment stays debuggable and rerunnable without database access. No other
  database use is permitted (Principle I non-goals).

Rationale: Inspectable JSON state makes the experiment debuggable, reproducible, and
cheap to rerun. A scoped Postgres store is admitted only to make the multi-dataset,
multi-seed ablation tractable, and only on the condition that it never becomes the sole
or opaque home of state.

### V. Anchored Synthetic Data Generation

Dataset expansion MUST be anchored to the original saved `data_spec` and performed
locally in Python without further LLM calls.

- Rows are expanded from the fixed seed spec; specs MUST NOT be recursively
  regenerated each round.
- Token usage MUST NOT scale with dataset size; growth happens in Python only.

Rationale: Recursive self-generated data loops reduce diversity and distort
distributions. Anchoring to a fixed seed spec is the safer, more reproducible design and keeps
cost bounded.

### VI. uv-Managed Python Environment

All Python dependency management and script execution MUST go through `uv`.

- Dependencies are declared and resolved with `uv` (e.g. `pyproject.toml` + `uv.lock`);
  `pip install`/`python -m venv` workflows MUST NOT be used.
- Every Python script or module is run via `uv run ...` (e.g. `uv run ds-agent-loop`,
  `uv run python -m ds_agent_loop.main`, `uv run python entrypoint/run.py`,
  `uv run pytest`), so the pinned environment is always used.

Rationale: A single, reproducible toolchain keeps the repo's environment consistent
and hackable without manual virtualenv bookkeeping — a baseline requirement for replayable
research (Principle IX).

### VII. Progress Communicated via notes/

Progress MUST be communicated back to the user through the `notes/` directory.

- Whenever a section/milestone of work is completed OR work is paused for a break, the
  exact current progress MUST be compiled into an HTML file under `notes/`.
- The `notes/` directory MUST be kept up to date more generally wherever it helps
  communicate status, decisions, or context back to the user.

Rationale: `notes/` is the shared, human-readable channel for status. Snapshotting
progress at natural boundaries keeps the user informed and makes the experiment easy to
resume.

### VIII. Typed Models & Centralized Settings (Pydantic)

Structured data and configuration MUST use Pydantic models, and runtime configuration
MUST be centralized.

- Where practical, the project's structured entities (e.g. the data spec, run/history
  records, the best run, and the LLM next-step decision) are represented as Pydantic
  models, and the LLM's structured outputs are validated through those models.
- Runtime configuration MUST live in a single centralized settings object built with
  `pydantic-settings` (loading from `.env` / environment), rather than ad-hoc constants
  scattered across modules.
- This MUST NOT be used to reintroduce complexity that violates Principle I: prefer a
  small number of focused models over a deep type hierarchy.

Rationale: Centralized, typed config and validated models reduce parsing/validation
boilerplate, catch malformed data early (reinforcing Principles II and III), and give a
single source of truth for configuration.

### IX. Reproducible & Replayable Experiments

Every experiment run MUST be fully reconstructable and replayable from persisted state. The
research claim depends on results that others — and future-you — can reproduce exactly.

- Every run MUST be uniquely identified and stamped with the full configuration needed to
  reproduce it: code/commit reference, settings snapshot, dataset id and split, random seeds,
  model/prompt/schema versions, and the memory/condition parameters of the experiment.
- Randomness MUST be seeded and recorded; given the same seed and inputs, deterministic steps
  (splitting, training, scoring) MUST reproduce identical results. Irreducible LLM
  non-determinism MUST be acknowledged and mitigated by running and reporting multiple seeds.
- A completed or interrupted run MUST be replayable from its persisted state (files + Postgres)
  WITHOUT recomputing already-finished work and without new LLM calls where prior outputs are
  already recorded.
- No result enters the research write-up unless the run that produced it is replayable from
  recorded state.

Rationale: Replayability is the difference between an anecdote and a research result. It makes
findings auditable, lets reviewers re-derive every number, and protects long multi-seed sweeps
from restarting on failure.

### X. Operational Reliability & Observability

The containerized experiment entrypoint MUST run flawlessly end-to-end, and every run MUST be
richly observable through structured logging persisted to and retrievable from Postgres.

- The `entrypoint/` + `Dockerfile` + root `docker-compose.yml` path MUST start cleanly, wait for
  its Postgres dependency to be healthy, run the configured experiment to completion, and exit
  with a correct status code — a single documented command (`docker compose up`) MUST work with no
  manual patching.
- Logging MUST be structured (machine-parseable, e.g. JSON lines), leveled, and cover run
  lifecycle, every iteration/decision, LLM calls, persistence operations, and failures with enough
  context to diagnose without a rerun. Logs MUST be emitted to stdout / `outputs/` AND persisted to
  Postgres so a run stays queryable and retrievable after the fact.
- Failures MUST be loud, specific, and fail-fast (consistent with the bounded-agency validation of
  Principle III); silent failure or silent truncation of state or context is prohibited. Retries,
  where used, MUST be bounded, logged, and MUST NOT mask non-reproducible behavior.
- Persistence to Postgres MUST be reliable and idempotent enough that a re-run or resume neither
  corrupts nor duplicates recorded experiment state (supports Principle IX).

Rationale: A research project that cannot be run reliably, or whose runs cannot be inspected after
the fact, cannot be trusted. Flawless, observable execution is what lets the experiment scale to
many datasets and seeds and still produce defensible numbers.

### XI. Research Rigor & Whitepaper Outcome

The project's deliverable is a rigorous research / whitepaper document, and engineering decisions
MUST serve that outcome.

- Standard engineering rigor applies even though this is research: tests for the deterministic
  machinery (data generation, training/scoring, persistence, replay), typed models (Principle
  VIII), reviewed changes, and reproducible environments (Principle VI) are REQUIRED, not optional.
- Experimental methodology MUST be pre-registered in the relevant `specs/` feature before a study
  is run: hypotheses, conditions, fixed factors, metrics, budgets, and analysis plan — so results
  are not retrofitted to a narrative.
- Every reported finding MUST be traceable to the persisted runs, logs, and analysis artifacts
  that produced it; figures, tables, and statistics MUST be regenerable from recorded state.
- Research narrative, status, and results are communicated through `notes/` (Principle VII) and
  compiled toward the eventual whitepaper; claims unsupported by replayable evidence MUST NOT be
  published.

Rationale: The value of the project is a credible research result. Applying real engineering
discipline — tests, pre-registration, traceability — to the research process is what makes the
eventual whitepaper trustworthy rather than a post-hoc story.

## Scope & Technology Constraints

- Language/stack: Python with scikit-learn for modeling. The LLM backend is Google Gemini on
  Vertex AI, accessed through Google's generative-AI SDK (`google.genai`) and driven by a
  minimal Google ADK agent (Principle I), using schema-constrained structured JSON output.
  The thin `llm.py` module wraps this backend so the rest of the library stays
  provider-agnostic. Structured entities and config use `pydantic` / `pydantic-settings`
  (Principle VIII).
- Provider configuration (Google Cloud project, location/region, credentials, and the Gemini
  model identifier) is supplied at run time via the centralized settings object and `.env` /
  environment; secrets MUST NOT be committed (documented via `.env.example`).
- Task scope is fixed: predict `delivery_time_minutes` from a small feature set
  (e.g. `item_count`, `distance_km`, `traffic_level`, `is_raining`, `hour_of_day`).
- Model comparison is limited to the allowlisted handful of regressors — not dozens.
- Evaluation MUST use `cross_validate` or a simple train/test split. Primary metric
  is RMSE; `R^2` and MAE are optional secondary metrics.
- The loop terminates after a fixed number of iterations `N` or after no improvement
  for `k` consecutive rounds.
- Dependencies stay minimal and are managed by `uv` (declared in `pyproject.toml`, pinned
  in `uv.lock`); see Principle VI.
- Persistence for the memory-compaction ablation harness MAY use a single Postgres instance
  (e.g. `postgres:17-alpine`), wired via a `DATABASE_URL` connection string supplied through the
  centralized settings / `.env` (Principle VIII). A root `docker-compose.yml` MAY orchestrate the
  backend together with this database for local runs; it MUST NOT bake in secrets, and ADC stays
  mounted read-only. This is the only sanctioned database use (Principles I & IV).
- Observability: runs MUST emit structured, leveled logs (e.g. JSON lines) covering lifecycle,
  per-iteration decisions, LLM/persistence operations, and failures; logs MUST be persisted to and
  retrievable from Postgres in addition to stdout / `outputs/` (Principle X).
- The containerized entrypoint (`Dockerfile` + `entrypoint/` + root `docker-compose.yml`) is the
  sanctioned way to run a full experiment and MUST work flawlessly via a single documented command,
  bringing up Postgres, running to completion, and exiting with a correct status (Principles IX, X).
  Long sweeps MUST be resumable from persisted state.

## Development Workflow

- Each iteration of `main.py` follows the fixed sequence: create seed data/spec if
  missing → expand dataset → train/evaluate one candidate → ask LLM for next step →
  save history → repeat until stop condition.
- Exactly one proposed change is evaluated per iteration; the loop stays intentionally
  small and dumb.
- Changes to module responsibilities, schemas, the model allowlist, state-file formats, or
  the scope of the permitted ADK agent MUST be checked against these principles before
  merging.
- Any added complexity MUST be justified against Principle I (Simplicity) or removed.
- Python is run only via `uv run python ...`, and dependencies are changed only through
  `uv` (Principle VI).
- The Docker entrypoint MUST be exercised, not just unit-tested: a change is not done until
  `docker compose up` runs the relevant experiment path cleanly end-to-end with structured logs
  landing in Postgres and a correct exit status (Principle X).
- New experiments MUST be pre-registered in `specs/` (hypotheses, conditions, fixed factors,
  metrics, analysis plan) before being run, and every reported result MUST be replayable from
  persisted state (Principles IX, XI).
- On finishing a section or pausing for a break, an HTML progress snapshot MUST be written
  to `notes/`, and `notes/` MUST be kept current as the user-facing status channel
  (Principle VII).
- Commit messages MUST NOT include a "Co-Authored-By: Claude" trailer or any equivalent
  AI co-author attribution.

## Governance

This constitution supersedes ad-hoc practice for this repository. It is the reference
for reviewing whether changes keep the project within its intended scope as a rigorous,
replayable research project.

- Amendments MUST be recorded by updating this file, including a Sync Impact Report
  and a version bump.
- Versioning follows semantic versioning:
  - MAJOR: backward-incompatible removal or redefinition of a principle or governance
    rule.
  - MINOR: a new principle/section or materially expanded guidance.
  - PATCH: clarifications, wording, or non-semantic refinements.
- Reviews (including any PR or self-review) MUST verify compliance with these
  principles, especially the bounded-agency and structured-output constraints, which
  are non-negotiable safety boundaries — and which the permitted ADK agent MUST honor.
  Reviews MUST additionally confirm that runs remain replayable from persisted state
  (Principle IX), that the containerized entrypoint executes flawlessly with structured logs
  persisted to Postgres (Principle X), and that every reported result is traceable to recorded
  runs (Principle XI).
- When a change conflicts with a principle, either the change is revised or the
  principle is formally amended first — silent deviations are not permitted.

**Version**: 4.0.0 | **Ratified**: 2026-06-13 | **Last Amended**: 2026-06-13
