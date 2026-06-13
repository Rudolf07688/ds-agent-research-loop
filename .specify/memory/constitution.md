<!--
SYNC IMPACT REPORT
==================
Version change: 1.3.0 → 2.0.0
Bump rationale: MAJOR — Principle I is redefined to PERMIT a single, minimal agent framework
  (Google ADK), which the prior version explicitly prohibited ("agent frameworks ... are
  prohibited"; Non-goal: "no multi-agent frameworks"). Relaxing a binding prohibition is a
  backward-incompatible governance change. The Scope & Technology Constraints section is also
  updated to name the LLM backend as Google Gemini on Vertex AI accessed via the `google.genai`
  SDK and hosted by a minimal ADK agent, replacing the prior OpenAI-compatible thin wrapper.
  Safety principles II (structured JSON only, two schemas) and III (bounded agency, no code
  execution) are UNCHANGED and now explicitly bound the permitted ADK agent.

Principles:
  I.    Simplicity & Readability First            (amended — single minimal ADK agent permitted)
  II.   Constrained LLM Contracts (Structured JSON Only)  (unchanged)
  III.  Bounded Agency (No Arbitrary Code Execution)      (unchanged)
  IV.   Inspectable & Reproducible State          (unchanged)
  V.    Anchored Synthetic Data Generation        (unchanged)
  VI.   uv-Managed Python Environment             (unchanged)
  VII.  Progress Communicated via notes/          (unchanged)
  VIII. Typed Models & Centralized Settings (Pydantic)   (unchanged)

Added sections: none
Removed sections: none

Templates / docs requiring review:
  ✅ .specify/memory/constitution.md (this file)
  ✅ .specify/templates/plan-template.md (generic Constitution Check gate — no change)
  ✅ .specify/templates/spec-template.md (no mandatory-section change)
  ✅ .specify/templates/tasks-template.md (no principle-driven category change)
  ✅ specs/002-live-tests-containerize/spec.md (already written against this amendment; FR-000
     prerequisite is now satisfied by v2.0.0)
  ⚠ README.md (documents the OpenAI-compatible setup + llm.py wrapper; reconcile to the
     Vertex AI / Gemini (google.genai) + minimal ADK backend when feature 002 is implemented)
  ⚠ .env.example (LLM_API_KEY / LLM_BASE_URL / LLM_MODEL vars; add Google Cloud project /
     location / Gemini-model / credentials vars when 002 is implemented)
  ⚠ specs/001-autods-loop/plan.md & data-model.md (describe the OpenAI-compatible client;
     historical — left as-is, superseded by 002)

Deferred TODOs: none
-->

# LLM Autonomous Data Scientist (Toy) Constitution

## Core Principles

### I. Simplicity & Readability First

The repository MUST prefer readability and short, single-purpose files over abstraction.
The project is a small offline toy experiment, not a production system or MLOps platform.

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
  ADK agent above, no background workers, databases, UI, prompt-versioning systems, or
  production-grade observability/auth/retries.

Rationale: The value of this repo is that it stays hackable and inspectable. Complexity
directly undermines its purpose. ADK is admitted only because the chosen backend (Gemini on
Vertex AI) is most naturally driven through it; admitting it minimally — and keeping it
fenced in by the structured-output and bounded-agency principles — preserves the toy's
inspectability while honoring the required technology.

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

- All durable state lives as plain files under `state/` (`data_spec.json`,
  `seed_rows.json`, `dataset.csv`, `history.json`, `best_run.json`); human-readable
  formats are required.
- Every run MUST be appended to `state/history.json` recording at minimum: iteration
  number, dataset size, model type, hyperparameters, metrics, LLM rationale, and
  timestamp.
- The best run MUST be persisted separately (`best_run.json`). A new run is accepted
  only when the primary metric (RMSE) improves.
- Seed/spec generation MUST be skipped when prior state already exists, so the loop
  can resume from checkpoints without redundant LLM calls.

Rationale: Inspectable JSON state makes the experiment debuggable, reproducible, and
cheap to rerun.

### V. Anchored Synthetic Data Generation

Dataset expansion MUST be anchored to the original saved `data_spec` and performed
locally in Python without further LLM calls.

- Rows are expanded from the fixed seed spec; specs MUST NOT be recursively
  regenerated each round.
- Token usage MUST NOT scale with dataset size; growth happens in Python only.

Rationale: Recursive self-generated data loops reduce diversity and distort
distributions. Anchoring to a fixed seed spec is the safer toy design and keeps cost
bounded.

### VI. uv-Managed Python Environment

All Python dependency management and script execution MUST go through `uv`.

- Dependencies are declared and resolved with `uv` (e.g. `pyproject.toml` + `uv.lock`);
  `pip install`/`python -m venv` workflows MUST NOT be used.
- Every Python script or module is run via `uv run ...` (e.g. `uv run ds-agent-loop`,
  `uv run python -m ds_agent_loop.main`, `uv run python entrypoint/run.py`,
  `uv run pytest`), so the pinned environment is always used.

Rationale: A single, reproducible toolchain keeps the toy repo's environment consistent
and hackable without manual virtualenv bookkeeping.

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
- On finishing a section or pausing for a break, an HTML progress snapshot MUST be written
  to `notes/`, and `notes/` MUST be kept current as the user-facing status channel
  (Principle VII).
- Commit messages MUST NOT include a "Co-Authored-By: Claude" trailer or any equivalent
  AI co-author attribution.

## Governance

This constitution supersedes ad-hoc practice for this repository. It is the reference
for reviewing whether changes keep the project within its intended toy scope.

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
- When a change conflicts with a principle, either the change is revised or the
  principle is formally amended first — silent deviations are not permitted.

**Version**: 2.0.0 | **Ratified**: 2026-06-13 | **Last Amended**: 2026-06-13
