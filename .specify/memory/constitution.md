<!--
SYNC IMPACT REPORT
==================
Version change: 5.1.0 → 5.2.0
Bump rationale (5.2.0): MINOR — adds binding persistence guidance: the Postgres schema MUST be
  managed with Alembic migrations (versioned, reviewed, applied deterministically) rather than ad-hoc
  DDL or a silent create_all in the operational path (amends Principle IV, the Scope persistence
  constraint, and the Development Workflow). Also registers
  notes/research/technical-guideline-high-level.md as a NON-binding implementation reference
  (memory-architecture guidance). No principle is removed or redefined and no scope is loosened, so
  the change is additive guidance.

Prior bump rationale (5.0.0 → 5.1.0): MINOR — adds one new binding Development-Workflow practice
  requiring that repository navigation and pre-change impact analysis go through the GitNexus MCP
  tools before any larger change. No principle is removed or redefined and no scope constraint is
  loosened, so the change is additive guidance rather than a breaking governance change.

Prior bump rationale (4.0.0 → 5.0.0): MAJOR — the project is re-pointed from a single fixed toy task toward a PhD-grade
  research thesis, **Directional Research Memory: Compaction as Momentum in Experiment Space**
  (see notes/research/paths/001-directional-research-memory-thesis-story.md). Two backward-
  incompatible scope redefinitions force the major bump: (a) the previously BINDING "task scope is
  fixed: predict delivery_time_minutes" single-dataset constraint is replaced by a multi-dataset
  BENCHMARK spanning regression AND classification with fixed train/val/test splits, fixed action
  space, and fixed per-dataset experiment budgets; (b) the model allowlist (Principle III) is
  widened from scikit-learn regressors only to a fixed allowlist of regressors AND classifiers.
  Three new principles elevate the thesis to first-class governance: XII Directional Research
  Memory (the compaction operator + outer compaction loop), XIII Memory as the Controlled
  Experimental Variable (the A/B/C regimes + exact "what was shown" provenance), and XIV Benchmark,
  Ablation & Phase-Transition Analysis (the directional/momentum hypothesis as the research target).
  The non-negotiable safety boundaries — Principle II (structured JSON only) and Principle III
  (bounded agency, no code execution) — are UNCHANGED in force; III's allowlist is merely widened
  to classifiers and stays fixed and developer-controlled.

Principles:
  I.    Simplicity & Readability First            (amended — serves the benchmark, not one toy task)
  II.   Constrained LLM Contracts (Structured JSON Only)  (unchanged)
  III.  Bounded Agency (No Arbitrary Code Execution)      (amended — allowlist widened to classifiers)
  IV.   Inspectable & Reproducible State          (amended — Postgres is now central, not optional)
  V.    Fixed, Versioned Benchmark Datasets       (amended — was "Anchored Synthetic Data Generation")
  VI.   uv-Managed Python Environment             (unchanged)
  VII.  Progress Communicated via notes/          (unchanged)
  VIII. Typed Models & Centralized Settings (Pydantic)   (unchanged)
  IX.   Reproducible & Replayable Experiments     (unchanged)
  X.    Operational Reliability & Observability    (unchanged)
  XI.   Research Rigor & Whitepaper Outcome        (amended — deliverable is the named thesis)
  XII.  Directional Research Memory               (NEW)
  XIII. Memory as the Controlled Experimental Variable   (NEW)
  XIV.  Benchmark, Ablation & Phase-Transition Analysis  (NEW)

Added sections: Principles XII, XIII, XIV
Removed sections: none (Principle V renamed and rescoped; single-task scope constraint removed)

Templates / docs requiring review:
  ✅ .specify/memory/constitution.md (this file — added GitNexus-MCP navigation/impact bullet to
     the Development Workflow section)
  ✅ CLAUDE.md (already mandates GitNexus impact analysis before edits — consistent with the new
     workflow bullet; no change required)
  ✅ .specify/templates/plan-template.md (generic "Gates determined based on constitution file" —
     no change; future plans evaluate against v5.0.0)
  ✅ .specify/templates/spec-template.md (no mandatory-section change)
  ✅ .specify/templates/tasks-template.md (generic categories cover benchmark/ablation/analysis
     tasks — no change)
  ⚠ specs/003-memory-compaction-ablation/spec.md (already pre-registers the A/B/C ablation + Postgres
     provenance; on re-plan, align its vocabulary to "Directional Research Memory", generalize from
     the single delivery-time dataset to the benchmark suite, and add the phase-transition /
     momentum-analysis acceptance criteria of Principles XII & XIV)
  ⚠ docker-compose.yml + Dockerfile + entrypoint/ (must run the benchmark suite flawlessly with
     structured logging persisted to Postgres — verify against Principles X & XIII)
  ⚠ README.md / .env.example (document the benchmark, the three memory regimes, the compaction
     artifact, and the replay/analysis workflow as those features land)

Reviewed for v5.2.0 (Alembic + reference doc):
  ✅ .specify/memory/constitution.md (Alembic schema-migration mandate added to Principle IV, the
     Scope persistence constraint, and the Development Workflow; technical-guideline reference
     registered in Governance)
  ✅ .specify/templates/{plan,spec,tasks}-template.md (generic, constitution-driven gates — no change;
     future plans evaluate the Alembic constraint against v5.2.0)
  ✅ notes/research/technical-guideline-high-level.md (registered as a NON-binding reference doc)
  ⚠ src/ds_agent_loop/store.py (currently builds tables via SQLAlchemy `metadata.create_all`; a
     follow-up MUST introduce an Alembic migration environment and restrict `create_all` to
     ephemeral/test schemas — see Principle IV. Not changed by this amendment.)

Deferred TODOs:
  - The multi-dataset benchmark suite, the memory-regime abstraction, the Directional Research
    Memory compaction operator, and the phase-transition analysis are pre-registered here as
    governance but implemented across forthcoming specs/ features (see roadmap), not by this
    amendment.
-->

# Directional Research Memory — Autonomous Data-Scientist Agent Constitution

This repository pursues a single research thesis: **Directional Research Memory — Compaction as
Momentum in Experiment Space.** An LLM-based data-scientist agent iteratively runs experiments;
the central claim under study is that, beyond a measurable threshold, adding more *raw* episodic
history HARMS performance, while replacing that raw history with a *structured, compact research
memory* improves both sample efficiency and final outcomes — behaving like optimization momentum
that preserves search direction while discarding noisy local detours. Every principle below exists
to make that claim either demonstrable or falsifiable with replayable evidence.

## Core Principles

### I. Simplicity & Readability First

The repository MUST prefer readability and short, single-purpose files over needless abstraction.
This is a rigorous, replayable RESEARCH project whose artifact is a benchmark and a thesis — not a
toy, and not a multi-tenant production platform. Simplicity-of-design is retained as an
anti-over-engineering guard, but it is SUBORDINATE to the reproducibility, reliability, and
observability the research goal demands (Principles IX–XIV): the code stays small and hackable,
while the experiment around it is engineered to research standards.

- The library is a small `src`-layout package (`src/ds_agent_loop/`) of single-purpose
  modules (`llm.py`, `data_gen.py`, `train.py`, `history.py`, `prompts.py`, `main.py`), plus the
  modules that the benchmark, the memory regimes, and the compaction operator concretely require
  (e.g. `memory.py`, `compaction.py`, `benchmark.py`). This single-purpose-module decomposition
  MUST be preserved; new modules earn their place by being concretely needed, not speculative.
- A SINGLE, MINIMAL agent framework — Google's Agent Development Kit (ADK) — is permitted,
  used ONLY to host the sanctioned LLM calls of Principle II. Its use MUST stay minimal:
  no additional tools, no autonomous actions, no multi-step planning or self-directed control
  flow beyond the fixed seed → next-step pattern. The ADK agent is bound by Principles II and
  III at all times. (This is a deliberate, bounded exception to the otherwise standing ban on
  frameworks.)
- Beyond that one permitted ADK agent, new indirection layers, additional agent frameworks,
  multi-agent systems, or general orchestration engines remain prohibited.
- Only a thin deployment consumer (`entrypoint/`) and runtime artifact directories
  (`state/`, `outputs/`, `notes/`, `entrypoint/runs/`) live outside the package. The
  consumer imports FROM the library, never the reverse; library logic MUST NOT leak into
  `entrypoint/`.
- YAGNI applies: features are added only when the benchmark or ablation concretely needs
  them. Speculative generality MUST be justified before introduction.
- Non-goals are binding: no multi-agent frameworks or orchestration beyond the single minimal
  ADK agent above, no web/GUI front-end, no authentication / multi-tenant concerns, no
  prompt-versioning systems, and no always-on background services beyond the batch experiment
  entrypoint. A SINGLE Postgres instance is the durable persistence backend for experiment,
  memory, and benchmark state under Principle IV; general-purpose or additional database use
  beyond that purpose remains out of scope.
- Comprehensive structured logging, a flawless containerized entrypoint, and bounded, logged
  retries where they aid reliable replay are REQUIRED by Principles IX and X. What stays out of
  scope is operational sprawl that does not serve reproducibility (auth, UIs, microservices,
  autoscaling, and the like).

Rationale: The repo stays hackable and inspectable, but it underwrites a research result, so
gratuitous complexity is rejected while reproducibility, reliability, and observability are
actively required. The seed delivery-time task remains a valid member of the benchmark, but the
project is no longer defined by it.

### II. Constrained LLM Contracts (Structured JSON Only)

Every LLM interaction MUST use a developer-supplied JSON schema. The sanctioned LLM jobs are a
small, fixed set: seed/dataset generation, next-experiment proposal, and — for the
compacted-memory regime only — research-memory compaction (Principle XII). No other LLM jobs are
permitted.

- The agent reasons over recorded metrics and the memory it is shown, and emits exactly one of
  the sanctioned structured proposals. It MUST NOT take on additional responsibilities. The
  permitted ADK agent (Principle I) MUST NOT expand to open-ended tool use.
- Free-form parsing of LLM output is prohibited; outputs MUST be schema-constrained structured
  JSON, validated through Pydantic models (Principle VIII).
- The next-step `action` MUST be one of the enumerated values of the benchmark's FIXED action
  space (e.g. `keep_model | tune_hyperparameters | switch_model | expand_dataset | stop`). The
  action space is held fixed across all memory regimes so that memory is the only manipulated
  variable (Principle XIII).

Rationale: Schema-constrained output keeps the LLM's role narrow and interpretable, removes
parser brittleness, and keeps the comparison across regimes clean.

### III. Bounded Agency (No Arbitrary Code Execution)

The LLM reasons over results; it MUST NOT execute or emit code that the system runs.

- The LLM MAY select models only from a FIXED, developer-controlled allowlist of scikit-learn
  estimators — regressors for regression datasets and classifiers for classification datasets.
  The allowlist stays small (a handful per task type), is identical across all memory regimes for
  a given dataset, and is versioned with the benchmark.
- The LLM MAY suggest only JSON configuration, never raw Python to be executed.
- Python MUST validate all proposed hyperparameters and model choices against the allowlist before
  training; invalid or out-of-allowlist proposals MUST be rejected, not silently coerced into
  execution.
- The permitted ADK agent MUST NOT be given tools, function-calling, or code-execution
  capabilities. Any agent "tools" are limited to the deterministic, developer-written steps of the
  fixed loop.

Rationale: This prevents the repo from degrading into an uncontrolled agent sandbox and keeps
every action auditable. Widening the allowlist to classifiers expands the benchmark's coverage
without loosening the bound — the set is still fixed, finite, and developer-owned.

### IV. Inspectable & Reproducible State

The experiment MUST be inspectable at every step and rerunnable from intermediate checkpoints.

- A SINGLE Postgres instance is the durable home of experiment, memory, and benchmark state:
  per-(dataset, seed, regime) trajectories, every experiment record, every compaction artifact and
  its source lineage, and — crucially — exactly what memory was shown to the agent before each
  decision (Principle XIII). The database schema MUST be documented.
- The Postgres schema MUST be managed with **Alembic** migrations: every schema change ships as a
  versioned, reviewed migration applied deterministically (`alembic upgrade head`) — never ad-hoc DDL
  or a silent `create_all` in the operational path. Migrations are part of the reproducible record
  (Principle IX): a fresh environment reaches the current schema by running them in order, and the
  schema version is recoverable from the migration history. A convenience `create_all` MAY be used
  only for ephemeral or test schemas.
- Postgres MUST NOT become an opaque or sole home of truth: its contents MUST remain inspectable
  and exportable to human-readable JSON/CSV, and the seed single-run path MAY still mirror core
  state as plain files under `state/` (`data_spec.json`, `seed_rows.json`, `dataset.csv`,
  `history.json`, `best_run.json`) for cheap local debugging.
- Every run MUST record at minimum: iteration number, dataset id and split, model type,
  hyperparameters, metrics, the memory regime and the exact memory shown, the LLM rationale, and a
  timestamp.
- The best run per (dataset, seed, regime) MUST be persisted separately; a new run is accepted as
  "best" only when the primary metric improves.
- Seed/spec generation and any already-computed step MUST be skippable when prior state exists, so
  the loop resumes from checkpoints without redundant or non-reproducible LLM calls.

Rationale: Inspectable, exportable state makes the experiment debuggable, reproducible, and cheap
to rerun, and makes the multi-dataset, multi-seed, multi-regime sweep tractable without ever
becoming an opaque black box.

### V. Fixed, Versioned Benchmark Datasets

Benchmark datasets and their splits MUST be fixed and versioned, and any synthetic data MUST be
anchored to a saved spec and generated locally in Python without further LLM calls.

- The benchmark is a versioned suite of tabular datasets (regression and classification) with
  FIXED train/validation/test splits and a fixed per-dataset experiment budget. Splits MUST be
  frozen and identical across all memory regimes and seeds so comparisons are fair.
- For synthetic datasets (including the seed delivery-time task), rows are expanded from a fixed
  saved `data_spec`; specs MUST NOT be recursively regenerated each round, and token usage MUST
  NOT scale with dataset size — growth happens in Python only.
- Adding or changing a benchmark dataset or split is a versioned change that MUST be recorded, so
  that any reported result names the exact benchmark version it was produced against.

Rationale: A fair memory-regime comparison and a credible phase-transition result both require
that the data, splits, and budgets are held constant while only memory varies. Anchoring synthetic
generation to a frozen spec keeps the data diverse, reproducible, and cheap.

### VI. uv-Managed Python Environment

All Python dependency management and script execution MUST go through `uv`.

- Dependencies are declared and resolved with `uv` (e.g. `pyproject.toml` + `uv.lock`);
  `pip install`/`python -m venv` workflows MUST NOT be used.
- Every Python script or module is run via `uv run ...` (e.g. `uv run ds-agent-loop`,
  `uv run python -m ds_agent_loop.main`, `uv run python entrypoint/run.py`, `uv run pytest`), so
  the pinned environment is always used.

Rationale: A single, reproducible toolchain keeps the environment consistent and hackable without
manual virtualenv bookkeeping — a baseline requirement for replayable research (Principle IX).

### VII. Progress Communicated via notes/

Progress MUST be communicated back to the user through the `notes/` directory.

- Whenever a section/milestone of work is completed OR work is paused for a break, the exact
  current progress MUST be compiled into an HTML file under `notes/`.
- The `notes/` directory MUST be kept up to date more generally wherever it helps communicate
  status, decisions, research direction, or context back to the user.

Rationale: `notes/` is the shared, human-readable channel for status and the staging ground for
the eventual thesis (Principle XI). Snapshotting progress at natural boundaries keeps the user
informed and makes the work easy to resume.

### VIII. Typed Models & Centralized Settings (Pydantic)

Structured data and configuration MUST use Pydantic models, and runtime configuration MUST be
centralized.

- The project's structured entities (data spec, run/history records, best run, the LLM next-step
  decision, the memory regime configuration, and the Directional Research Memory compaction
  artifact) are represented as Pydantic models, and the LLM's structured outputs are validated
  through those models.
- Runtime configuration MUST live in a single centralized settings object built with
  `pydantic-settings` (loading from `.env` / environment), rather than ad-hoc constants scattered
  across modules.
- This MUST NOT be used to reintroduce complexity that violates Principle I: prefer a small number
  of focused models over a deep type hierarchy.

Rationale: Centralized, typed config and validated models reduce boilerplate, catch malformed data
early (reinforcing Principles II and III), and give a single source of truth for configuration.

### IX. Reproducible & Replayable Experiments

Every experiment run MUST be fully reconstructable and replayable from persisted state. The
research claim depends on results that others — and future-you — can reproduce exactly.

- Every run MUST be uniquely identified and stamped with the full configuration needed to
  reproduce it: code/commit reference, settings snapshot, benchmark version, dataset id and split,
  random seeds, model/prompt/schema versions, and the memory regime and its parameters.
- Randomness MUST be seeded and recorded; given the same seed and inputs, deterministic steps
  (splitting, training, scoring, compaction inputs) MUST reproduce identical results. Irreducible
  LLM non-determinism MUST be acknowledged and mitigated by running and reporting multiple seeds.
- A completed or interrupted run MUST be replayable from its persisted state WITHOUT recomputing
  finished work and without new LLM calls where prior outputs are already recorded.
- No result enters the research write-up unless the run that produced it is replayable from
  recorded state.

Rationale: Replayability is the difference between an anecdote and a research result. It makes
findings auditable, lets reviewers re-derive every number, and protects long multi-seed,
multi-regime sweeps from restarting on failure.

### X. Operational Reliability & Observability

The containerized experiment entrypoint MUST run flawlessly end-to-end, and every run MUST be
richly observable through structured logging persisted to and retrievable from Postgres.

- The `entrypoint/` + `Dockerfile` + root `docker-compose.yml` path MUST start cleanly, wait for
  its Postgres dependency to be healthy, run the configured benchmark/ablation to completion, and
  exit with a correct status code — a single documented command (`docker compose up`) MUST work
  with no manual patching.
- Logging MUST be structured (machine-parseable, e.g. JSON lines), leveled, and cover run
  lifecycle, every iteration/decision, the memory shown, LLM calls, compaction events, persistence
  operations, and failures with enough context to diagnose without a rerun. Logs MUST be emitted to
  stdout / `outputs/` AND persisted to Postgres so a run stays queryable after the fact.
- Failures MUST be loud, specific, and fail-fast (consistent with Principle III); silent failure or
  silent truncation of state or context is prohibited. Retries, where used, MUST be bounded,
  logged, and MUST NOT mask non-reproducible behavior.
- Persistence MUST be reliable and idempotent enough that a re-run or resume neither corrupts nor
  duplicates recorded state (supports Principle IX).

Rationale: A research project that cannot be run reliably, or whose runs cannot be inspected after
the fact, cannot be trusted. Flawless, observable execution is what lets the experiment scale to
many datasets, seeds, and regimes and still produce defensible numbers.

### XI. Research Rigor & Whitepaper Outcome

The project's deliverable is the rigorous thesis **Directional Research Memory for Autonomous
Data-Scientist Agents: Compaction as Momentum in Experiment Space**, and engineering decisions
MUST serve that outcome.

- Standard engineering rigor applies even though this is research: tests for the deterministic
  machinery (data generation, training/scoring, persistence, replay, the compaction operator's
  deterministic parts), typed models (Principle VIII), reviewed changes, and reproducible
  environments (Principle VI) are REQUIRED, not optional.
- Experimental methodology MUST be pre-registered in the relevant `specs/` feature before a study
  is run: hypotheses, conditions/regimes, fixed factors, metrics, budgets, and analysis plan — so
  results are not retrofitted to a narrative.
- Every reported finding MUST be traceable to the persisted runs, logs, and analysis artifacts that
  produced it; figures, tables, and statistics MUST be regenerable from recorded state.
- Research narrative, status, and results are communicated through `notes/` (Principle VII) and
  compiled toward the eventual thesis; claims unsupported by replayable evidence MUST NOT be
  published.

Rationale: The value of the project is a credible research result. Applying real engineering
discipline — tests, pre-registration, traceability — to the research process is what makes the
eventual thesis trustworthy rather than a post-hoc story.

### XII. Directional Research Memory

The central object of study is **Directional Research Memory**: a structured, compact projection of
the raw experiment trajectory onto a low-dimensional set of stable beliefs. It MUST be defined as a
specific schema, not as a generic free-form summary.

- The compaction artifact MUST be a typed, schema-constrained structure (Principle VIII) capturing
  at minimum: what is probably TRUE, what has likely FAILED, what remains UNRESOLVED, and which
  broad DIRECTIONS in experiment space are worth pursuing next. Free-form prose alone does not
  satisfy this principle.
- Compaction runs in an OUTER loop, distinct from the inner experiment loop: the system periodically
  rereads the recorded trajectory and (re)generates the artifact, rather than appending to an
  ever-growing raw history. The compaction cadence MUST be an explicit, recorded parameter.
- Compaction MUST be the only third sanctioned LLM job (Principle II) and MUST be bounded by the
  same structured-output and no-code-execution constraints (Principles II–III). Its inputs and
  outputs MUST be persisted with full lineage so any artifact can be traced to the raw runs it
  summarized (Principle IV).
- Directional Research Memory MUST be treated as a noisy estimate of where the search should move
  next — it preserves DIRECTION while discarding local zig-zags — and MUST NOT silently drop signal
  in a way that cannot be audited against the raw trajectory it replaced.

Rationale: The thesis stands or falls on a precise, inspectable definition of the compaction
operator. Pinning it to a stable belief schema and an explicit outer loop is what turns "summaries
help" into a testable claim about directional preservation.

### XIII. Memory as the Controlled Experimental Variable

Across any comparison, the memory regime MUST be the ONLY manipulated variable, and exactly what
memory the agent saw before each decision MUST be recorded.

- The harness MUST support at least three swappable memory regimes behind one interface:
  recent-only (last `k` raw records), all-raw (the full raw history), and compacted+recent (one
  Directional Research Memory artifact plus a short tail of fresh raw runs). Regimes are
  configuration, not forks of the loop.
- For a given (dataset, seed), everything else — agent, prompts, action space, model allowlist,
  budget, splits, scoring — MUST be held identical across regimes; the regime MUST change only the
  slice of memory presented to the agent.
- The EXACT memory shown to the agent before every decision MUST be persisted (content or a
  content-addressable reference), so any decision is replayable and the regimes are auditable
  against each other (Principles IX, IV).

Rationale: A clean causal claim about memory requires that memory is the sole intervention and that
"what the agent actually saw" is never reconstructed after the fact from guesswork. This is the
experimental backbone of the thesis.

### XIV. Benchmark, Ablation & Phase-Transition Analysis

The research target is not merely "which regime wins" but the directional/momentum story:
where, and why, raw history starts to hurt. The benchmark and analysis MUST be built to expose
that.

- Studies MUST run the regimes (Principle XIII) across the multi-dataset benchmark (Principle V)
  over multiple seeds, with paired comparisons and appropriate significance testing — not a single
  cherry-picked run.
- The analysis MUST go beyond final scores to characterize the TRAJECTORY: sample efficiency
  (score vs. experiments used), proposal diversity / collapse, repetition of failed ideas, and a
  regret-style measure of wasted search — the quantities through which "momentum" is made
  measurable rather than metaphorical.
- The work MUST attempt to locate the PHASE TRANSITION: the threshold of accumulated raw history
  beyond which adding more harms performance. If a clear threshold is not found, that null/partial
  result MUST be reported faithfully (Principle XI); the analysis MUST NOT be tuned to manufacture
  one.
- Any theoretical treatment (e.g. linking the compaction operator to momentum / regret reduction)
  MUST state its simplifying assumptions explicitly and MUST be consistent with the empirical
  results, not a substitute for them.

Rationale: The contribution is the directional-preservation framing, the identified threshold, and
the link between memory and optimization — not a leaderboard. Governing the analysis toward
trajectory and threshold quantities is what keeps the eventual thesis honest and PhD-worthy.

## Scope & Technology Constraints

- Language/stack: Python with scikit-learn for modeling (regressors and classifiers, Principle III).
  The LLM backend is Google Gemini on Vertex AI, accessed through Google's generative-AI SDK
  (`google.genai`) and driven by a minimal Google ADK agent (Principle I), using schema-constrained
  structured JSON output. The thin `llm.py` module wraps this backend so the rest of the library
  stays provider-agnostic. Structured entities and config use `pydantic` / `pydantic-settings`
  (Principle VIII).
- Provider configuration (Google Cloud project, location/region, credentials, and the Gemini model
  identifier) is supplied at run time via the centralized settings object and `.env` / environment;
  secrets MUST NOT be committed (documented via `.env.example`).
- Benchmark scope: a versioned suite of tabular regression and classification datasets with fixed
  train/validation/test splits and fixed per-dataset experiment budgets (Principle V). The seed
  delivery-time regression task (predicting `delivery_time_minutes` from a small feature set such as
  `item_count`, `distance_km`, `traffic_level`, `is_raining`, `hour_of_day`) remains one member of
  the suite, not the whole of it.
- Model comparison is limited to the fixed, versioned allowlist of a handful of regressors and a
  handful of classifiers — not dozens, and never open-ended.
- Evaluation uses the fixed splits (or `cross_validate` where a study calls for it). Primary metrics
  are task-appropriate (e.g. RMSE for regression, a fixed classification metric such as accuracy or
  F1 for classification), declared per dataset; secondary metrics are optional but must be declared.
- Each per-dataset loop terminates after that dataset's fixed budget `N` of iterations or after no
  improvement for `k` consecutive rounds, whichever the study pre-registers.
- Memory regimes (recent-only / all-raw / compacted+recent) are first-class configuration
  (Principle XIII); the compacted regime uses the Directional Research Memory artifact and outer
  compaction loop (Principle XII).
- Persistence uses a single Postgres instance (e.g. `postgres:17-alpine`), wired via a
  `DATABASE_URL` connection string supplied through the centralized settings / `.env`. A root
  `docker-compose.yml` orchestrates the backend together with this database for local runs; it MUST
  NOT bake in secrets, and ADC stays mounted read-only. This is the only sanctioned database use
  (Principles I & IV). Tables are defined with SQLAlchemy Core and the schema is created and evolved
  exclusively through **Alembic** migrations (`alembic`, declared in `pyproject.toml`); see
  Principle IV.
- Observability: runs MUST emit structured, leveled logs (e.g. JSON lines) covering lifecycle,
  per-iteration decisions, the memory shown, compaction events, LLM/persistence operations, and
  failures; logs MUST be persisted to and retrievable from Postgres in addition to stdout /
  `outputs/` (Principle X).
- The containerized entrypoint (`Dockerfile` + `entrypoint/` + root `docker-compose.yml`) is the
  sanctioned way to run a benchmark/ablation and MUST work flawlessly via a single documented
  command, bringing up Postgres, running to completion, and exiting with a correct status
  (Principles IX, X). Long sweeps MUST be resumable from persisted state.
- Dependencies stay minimal and are managed by `uv` (declared in `pyproject.toml`, pinned in
  `uv.lock`); see Principle VI.

## Development Workflow

- Each inner iteration follows the fixed sequence: ensure seed data/spec for the dataset → expand
  data if the action calls for it → train/evaluate exactly one candidate → present the
  regime-appropriate memory → ask the LLM for the next step → persist the run and the exact memory
  shown → repeat until the stop condition.
- The outer compaction loop (compacted regime only) runs on its recorded cadence: reread the
  trajectory → (re)generate the Directional Research Memory artifact → persist it with lineage
  (Principle XII).
- Exactly one proposed change is evaluated per inner iteration; the loop stays intentionally small.
- Changes to module responsibilities, schemas, the action space, the model allowlist, the memory
  regimes, the compaction schema, benchmark datasets/splits, state formats, or the scope of the
  permitted ADK agent MUST be checked against these principles before merging.
- Any added complexity MUST be justified against Principle I (Simplicity) or removed.
- Repository navigation and pre-change impact analysis MUST go through the GitNexus MCP tools:
  before any larger change (touching a function/class/method, a schema, the action space, the
  loop, the memory regimes, or persistence), the affected symbol's blast radius MUST be assessed
  with GitNexus impact analysis and any HIGH/CRITICAL risk surfaced before proceeding; unfamiliar
  code MUST be explored via GitNexus rather than ad-hoc grepping.
- Any change to the Postgres schema MUST ship as an **Alembic migration** in the same change and be
  applied with `alembic upgrade head`; reviews reject schema drift that bypasses a migration, and a
  `create_all` outside ephemeral/test paths is a violation (Principle IV).
- Python is run only via `uv run python ...`, and dependencies are changed only through `uv`
  (Principle VI).
- The Docker entrypoint MUST be exercised, not just unit-tested: a change is not done until
  `docker compose up` runs the relevant benchmark/ablation path cleanly end-to-end with structured
  logs landing in Postgres and a correct exit status (Principle X).
- New studies MUST be pre-registered in `specs/` (hypotheses, regimes, fixed factors, metrics,
  budgets, analysis plan) before being run, and every reported result MUST be replayable from
  persisted state (Principles IX, XI, XIV).
- On finishing a section or pausing for a break, an HTML progress snapshot MUST be written to
  `notes/`, and `notes/` MUST be kept current as the user-facing status channel (Principle VII).
- Commit messages MUST NOT include a "Co-Authored-By: Claude" trailer or any equivalent AI
  co-author attribution.

## Governance

This constitution supersedes ad-hoc practice for this repository. It is the reference for reviewing
whether changes keep the project within its intended scope as a rigorous, replayable research
project pursuing the Directional Research Memory thesis.

- Amendments MUST be recorded by updating this file, including a Sync Impact Report and a version
  bump.
- Versioning follows semantic versioning:
  - MAJOR: backward-incompatible removal or redefinition of a principle, governance rule, or
    binding scope constraint.
  - MINOR: a new principle/section or materially expanded guidance.
  - PATCH: clarifications, wording, or non-semantic refinements.
- Reviews (including any PR or self-review) MUST verify compliance with these principles, especially
  the bounded-agency and structured-output constraints, which are non-negotiable safety boundaries —
  and which the permitted ADK agent MUST honor. Reviews MUST additionally confirm that memory is the
  sole manipulated variable with exact "what was shown" provenance (Principle XIII), that the
  Directional Research Memory artifact conforms to its belief schema and outer-loop discipline
  (Principle XII), that runs remain replayable from persisted state (Principle IX), that the
  containerized entrypoint executes flawlessly with structured logs persisted to Postgres
  (Principle X), and that every reported result is traceable to recorded runs (Principles XI, XIV).
- When a change conflicts with a principle, either the change is revised or the principle is formally
  amended first — silent deviations are not permitted.
- Implementation-level technical guidance — notably the memory-architecture notes in
  `notes/research/technical-guideline-high-level.md` (the async durable-memory vs. sync planner-time
  context split, Postgres as source of truth, an optional semantic-retrieval layer, and versioned
  structured compaction) — is a NON-binding REFERENCE that informs design but does NOT override these
  principles. Where the reference and the constitution diverge, the constitution governs.

**Version**: 5.2.0 | **Ratified**: 2026-06-13 | **Last Amended**: 2026-06-13
