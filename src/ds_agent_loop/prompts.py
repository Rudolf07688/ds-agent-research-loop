"""Typed entities, centralized settings, JSON schemas, and prompt text.

This module is the single home for the project's Pydantic models (Constitution
Principle VIII), the one ``pydantic-settings`` configuration object, the two sanctioned
LLM JSON schemas (Principle II), and the prompt templates that drive the two LLM calls.
Keeping these together honours the fixed flat module list (no extra ``config.py``).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# ---------------------------------------------------------------------------
# Structured entities (Pydantic models) — validate LLM output and on-disk state
# ---------------------------------------------------------------------------


class DeliveryRecord(BaseModel):
    """A single synthetic delivery observation (one dataset row)."""

    model_config = ConfigDict(extra="forbid")

    item_count: int = Field(ge=1)
    distance_km: float = Field(ge=0)
    traffic_level: str
    is_raining: bool
    hour_of_day: int = Field(ge=0, le=23)
    delivery_time_minutes: float = Field(ge=0)


class DataSpec(BaseModel):
    """LLM-authored, reusable spec that anchors all local expansion."""

    model_config = ConfigDict(extra="forbid")

    features: list[str] = Field(min_length=1)
    target: str = Field(default="delivery_time_minutes")
    rules: list[str]
    categories: dict[str, list[str]]
    noise_level: float = Field(ge=0)


class SeedGeneration(BaseModel):
    """Structured output of the seed-generation call."""

    model_config = ConfigDict(extra="forbid")

    seed_rows: list[DeliveryRecord] = Field(min_length=1)
    data_spec: DataSpec


class NextAction(str, Enum):
    keep_model = "keep_model"
    tune_hyperparameters = "tune_hyperparameters"
    switch_model = "switch_model"
    expand_dataset = "expand_dataset"
    stop = "stop"


class NextStepDecision(BaseModel):
    """Constrained next-step proposal from the LLM. Never executed as code."""

    model_config = ConfigDict(extra="forbid")

    action: NextAction
    model_name: str = ""
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    notes: list[str] = Field(default_factory=list)


class MemoryRegime(str, Enum):
    """The single manipulated variable of the ablation (Principle XIII)."""

    recent_only = "recent_only"
    all_raw = "all_raw"
    compacted_recent = "compacted_recent"


class TaskType(str, Enum):
    """Benchmark task family (Principle V)."""

    regression = "regression"
    classification = "classification"


class CellStatus(str, Enum):
    """Lifecycle of one sweep cell. ``completed``, ``context_limited`` and ``failed``
    are terminal — a terminal cell is never recomputed on resume (SC-007)."""

    pending = "pending"
    running = "running"
    completed = "completed"
    context_limited = "context_limited"  # Condition B hit the model context wall (clarification 2026-06-13)
    failed = "failed"


class RunRecord(BaseModel):
    """One iteration's outcome; the atomic unit of history and logging (FR-013).

    The original toy-loop fields (``iteration``..``timestamp``) are unchanged so existing
    ``state/history.json`` still validates and the single-dataset path keeps working. The
    feature-003 ablation adds optional per-cell provenance fields; they default to ``None``/
    empty so a plain toy run leaves them unset.
    """

    model_config = ConfigDict(extra="forbid")

    iteration: int
    dataset_size: int
    model_name: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float]
    rationale: str
    timestamp: str

    # --- feature 003: ablation provenance (data-model.md §ExperimentRecord) -----
    cell_id: str | None = None
    dataset_id: str | None = None
    regime: MemoryRegime | None = None
    seed: int | None = None
    k: int | None = None
    m: int | None = None
    proposal: NextStepDecision | None = None
    executed_config: dict[str, Any] = Field(default_factory=dict)
    val_metrics: dict[str, float] = Field(default_factory=dict)
    test_metrics: dict[str, float] = Field(default_factory=dict)
    improved: bool = False
    rejected: bool = False
    memory_view_ref: str | None = None
    runtime_s: float | None = None


# ``ExperimentRecord`` is ``RunRecord`` with the ablation fields populated. Aliased so
# callers can use the intention-revealing name from the data model.
ExperimentRecord = RunRecord


class MemoryView(BaseModel):
    """The exact memory slice shown to the agent at one decision (Principle XIII).

    Persisted before the agent decides so every decision is replayable and the regimes are
    auditable against each other (FR-013). ``memory.build_view`` is the only constructor.
    """

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    iteration: int
    regime: MemoryRegime
    included_record_ids: list[int] = Field(default_factory=list)
    included_artifact_id: str | None = None
    rendered_text: str
    content_hash: str
    prompt_token_count: int


class ReplayMismatch(BaseModel):
    """One decision whose replayed memory view diverged from what was persisted (FR-009)."""

    model_config = ConfigDict(extra="forbid")

    iteration: int
    expected_hash: str  # the stored MemoryView.content_hash / ExperimentRecord.memory_view_ref
    actual_hash: str  # the hash of the view rebuilt from persisted history


class ReplayResult(BaseModel):
    """Outcome of verifying a cell's decisions are replayable from persisted state (US3, FR-008/009)."""

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    total: int = 0
    matched: int = 0
    mismatches: list[ReplayMismatch] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.total == self.matched and not self.mismatches


class AuditResult(BaseModel):
    """Outcome of auditing two cells as a memory-only comparison (US4, FR-010/011)."""

    model_config = ConfigDict(extra="forbid")

    cell_a: str
    cell_b: str
    same_member_seed: bool
    fingerprint_equal: bool = False
    differing_factor: str | None = None  # first contaminating held-fixed factor, if any
    differing_dimension: str = ""  # the intended difference, e.g. "regime: recent_only -> all_raw"
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.same_member_seed and self.fingerprint_equal


class ExperimentCell(BaseModel):
    """One ``(dataset × regime × seed × k × m)`` sweep unit (FR-014, Principles IX/XIII)."""

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    dataset_id: str
    regime: MemoryRegime
    seed: int
    k: int
    m: int
    budget: int
    status: CellStatus = CellStatus.pending
    error: str | None = None
    # Iteration reached; for ``context_limited`` this is where Condition B hit the wall and
    # the remaining budget is recorded as not-run (clarification 2026-06-13).
    last_iteration: int | None = None
    repro: dict[str, Any] = Field(default_factory=dict)
    created_ts: str | None = None
    updated_ts: str | None = None


# ---------------------------------------------------------------------------
# Centralized settings (the single pydantic-settings object) — Principle VIII
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Single source of truth for runtime config; loaded from ``.env``/environment.

    CLI flags override these at call time (see ``main.py``). Field names map to
    upper-case environment variables (e.g. ``gemini_model`` -> ``GEMINI_MODEL``).

    The LLM backend is Google Gemini on Vertex AI via ``google.genai`` + a minimal ADK
    agent. Authentication is Application Default Credentials (ADC), discovered from the
    environment — it is intentionally NOT a settings field and is never persisted here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_cloud_project: str = "research-se-gen-ai"
    google_cloud_location: str = "global"
    gemini_model: str = "gemini-3.5-flash"
    use_vertexai: bool = True

    n_iterations: int = 30
    patience: int = 3
    target_size: int = 500
    primary_metric: str = "rmse"

    # --- Memory-compaction ablation (feature 003) -----------------------------
    # Postgres connection (Principle IV). Driver-agnostic form accepted; store.py
    # normalizes a bare ``postgresql://`` URL to the psycopg driver.
    database_url: str = "postgresql+psycopg://autods:autods@localhost:5432/autods"
    # Stamped onto every cell so a result names the benchmark version it ran against.
    benchmark_version: str = "v1"
    # Sweep factors. Empty ``datasets`` means "the full suite". List fields also accept
    # a comma-separated string from the environment (see ``_split_csv`` below).
    # ``NoDecode`` tells pydantic-settings NOT to JSON-decode these from the environment, so
    # the ``_split_csv`` validator below can accept a comma-separated string (e.g.
    # ``DATASETS=delivery_time,diabetes``) as well as a real list.
    datasets: Annotated[list[str], NoDecode] = Field(default_factory=list)
    regimes: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["recent_only", "all_raw", "compacted_recent"]
    )
    seeds: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    # Single-run memory regime (feature 005, FR-002): the regime is pure configuration, selected
    # per run via ``REGIME`` (the loop body has no regime branch beyond the build_view seam). Typed
    # as the enum so an unknown/malformed value fails fast at ``Settings()`` construction — never a
    # silent default. The sweep path keeps the ``regimes`` list above.
    regime: MemoryRegime = MemoryRegime.recent_only
    recent_k: int = 5
    compaction_m: int = 10
    # Optional FR-024 secondary trigger; off by default.
    compaction_token_threshold: int | None = None

    @field_validator("datasets", "regimes", "seeds", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept ``"a,b,c"`` from the environment for the list-valued sweep factors."""

        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


# ---------------------------------------------------------------------------
# The two sanctioned LLM JSON schemas (Principle II) — kept here, not free-form
# ---------------------------------------------------------------------------

SEED_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["seed_rows", "data_spec"],
    "properties": {
        "seed_rows": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "item_count",
                    "distance_km",
                    "traffic_level",
                    "is_raining",
                    "hour_of_day",
                    "delivery_time_minutes",
                ],
                "properties": {
                    "item_count": {"type": "integer", "minimum": 1},
                    "distance_km": {"type": "number", "minimum": 0},
                    "traffic_level": {"type": "string"},
                    "is_raining": {"type": "boolean"},
                    "hour_of_day": {"type": "integer", "minimum": 0, "maximum": 23},
                    "delivery_time_minutes": {"type": "number", "minimum": 0},
                },
            },
        },
        "data_spec": {
            "type": "object",
            "additionalProperties": False,
            "required": ["features", "target", "rules", "categories", "noise_level"],
            "properties": {
                "features": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "target": {"type": "string", "const": "delivery_time_minutes"},
                "rules": {"type": "array", "items": {"type": "string"}},
                "categories": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": {"type": "string"}},
                },
                "noise_level": {"type": "number", "minimum": 0},
            },
        },
    },
}

NEXT_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "model_name", "hyperparameters", "reason", "notes"],
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "keep_model",
                "tune_hyperparameters",
                "switch_model",
                "expand_dataset",
                "stop",
            ],
        },
        "model_name": {"type": "string"},
        "hyperparameters": {"type": "object", "additionalProperties": True},
        "reason": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


# ---------------------------------------------------------------------------
# Prompt text
# ---------------------------------------------------------------------------

SEED_GENERATION_SYSTEM = (
    "You are a data generation assistant for a toy machine-learning experiment. "
    "You design a small, realistic dataset about food-delivery times and a compact, "
    "reusable spec that a Python program will use to generate more rows locally. "
    "Return only structured JSON conforming to the provided schema."
)

SEED_GENERATION_USER = (
    "Produce a seed sample plus a reusable data_spec for predicting "
    "`delivery_time_minutes` from these features: item_count (int >= 1), "
    "distance_km (float >= 0), traffic_level (categorical), is_raining (bool), "
    "hour_of_day (int 0-23).\n\n"
    "Requirements:\n"
    "- Provide 12-20 realistic seed_rows with plausible delivery times.\n"
    "- In data_spec: list the 5 feature names; set target to "
    "'delivery_time_minutes'; give `categories` for every categorical feature "
    "(e.g. traffic_level: [low, medium, high]); write clear human-readable `rules` "
    "describing how delivery time depends on the features so Python can reproduce "
    "the relationship; set a small positive `noise_level` for additive target noise.\n"
    "- The spec must be self-contained: Python will expand the dataset from it with "
    "no further LLM calls."
)

NEXT_STEP_SYSTEM = (
    "You are guiding a toy AutoML loop. You reason over recorded run metrics and "
    "propose exactly ONE next action. You may only choose a model from the provided "
    "allowlist and may only emit JSON configuration — never code. Python validates "
    "and executes your proposal; invalid proposals are rejected. Return only "
    "structured JSON conforming to the provided schema."
)


def next_step_user(history_json: str, allowlist: list[str], best_summary: str) -> str:
    """Build the next-step user prompt from recorded history and the allowlist."""

    return (
        "Allowed models (model_name MUST be one of these): "
        f"{', '.join(allowlist)}.\n\n"
        "Allowed actions: keep_model, tune_hyperparameters, switch_model, "
        "expand_dataset, stop.\n\n"
        f"Best run so far: {best_summary}\n\n"
        "Run history (most recent last):\n"
        f"{history_json}\n\n"
        "Choose the single next action most likely to lower RMSE. When the action is "
        "switch_model or keep_model, set model_name to an allowed model. When the "
        "action is tune_hyperparameters, put the proposed hyperparameters in "
        "`hyperparameters` (JSON only, valid scikit-learn keyword arguments for the "
        "current model). Give a short `reason`."
    )


# --- feature 003: generic, dataset-aware next-step prompt (action space unchanged) ----
# The prompt template, schema and action space are held FIXED across the three regimes
# (SC-002); only the *memory* text injected differs. The metric name/direction generalize
# so the same contract serves regression and classification benchmark members.

ABLATION_NEXT_STEP_SYSTEM = (
    "You are guiding a controlled AutoML experiment loop over a fixed tabular dataset. "
    "You reason ONLY over the memory you are shown and the dataset summary, and propose "
    "exactly ONE next action. You may only choose a model from the provided allowlist and "
    "may only emit JSON configuration — never code. Python validates and executes your "
    "proposal; invalid proposals are rejected. Return only structured JSON conforming to "
    "the provided schema."
)


def ablation_next_step_user(
    memory_text: str,
    allowlist: list[str],
    best_summary: str,
    *,
    dataset_summary: str,
    metric: str,
    goal_word: str,
) -> str:
    """Next-step prompt for the ablation. ``memory_text`` is the regime-specific view."""

    return (
        f"Dataset: {dataset_summary}\n"
        f"Primary metric: {metric} (goal: {goal_word} it).\n\n"
        "Allowed models (model_name MUST be one of these): "
        f"{', '.join(allowlist)}.\n\n"
        "Allowed actions: keep_model, tune_hyperparameters, switch_model, "
        "expand_dataset, stop.\n\n"
        f"Best so far: {best_summary}\n\n"
        "Memory (what you know about the experiments so far):\n"
        f"{memory_text}\n\n"
        f"Choose the single next action most likely to {goal_word} the {metric}. For "
        "switch_model/keep_model set model_name to an allowed model; for "
        "tune_hyperparameters put valid scikit-learn keyword arguments in `hyperparameters` "
        "(JSON only). Give a short `reason`."
    )


# ---------------------------------------------------------------------------
# Directional Research Memory — the compaction artifact (Principle XII, FR-007)
# The THIRD sanctioned structured-JSON job (Principle II). A belief-schema projection of
# the raw trajectory, NOT a free-form summary.
# ---------------------------------------------------------------------------


class BestKnownConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metric: float


class DirectionalMemory(BaseModel):
    """Structured, compact projection of the raw experiment trajectory onto stable beliefs."""

    model_config = ConfigDict(extra="forbid")

    confirmed_findings: list[str] = Field(default_factory=list)
    failed_directions: list[str] = Field(default_factory=list)
    promising_directions: list[str] = Field(default_factory=list)
    best_known_configs: list[BestKnownConfig] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    next_step_recommendation: str
    confidence: float = Field(ge=0, le=1)
    rationale: str


COMPACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "confirmed_findings", "failed_directions", "promising_directions",
        "best_known_configs", "unresolved_questions", "next_step_recommendation",
        "confidence", "rationale",
    ],
    "properties": {
        "confirmed_findings": {"type": "array", "items": {"type": "string"}},
        "failed_directions": {"type": "array", "items": {"type": "string"}},
        "promising_directions": {"type": "array", "items": {"type": "string"}},
        "best_known_configs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["model_name", "hyperparameters", "metric"],
                "properties": {
                    "model_name": {"type": "string"},
                    "hyperparameters": {"type": "object", "additionalProperties": True},
                    "metric": {"type": "number"},
                },
            },
        },
        "unresolved_questions": {"type": "array", "items": {"type": "string"}},
        "next_step_recommendation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
    },
}

COMPACTION_SYSTEM = (
    "You are the research memory of an autonomous data-scientist run. You read the raw "
    "trajectory of experiments so far and project it onto a small set of STABLE BELIEFS: "
    "what is probably TRUE (confirmed_findings), what has likely FAILED (failed_directions), "
    "which broad DIRECTIONS are worth pursuing next (promising_directions), the best configs "
    "seen, what remains UNRESOLVED, and a single next-step recommendation. You preserve "
    "search DIRECTION while discarding noisy local detours. Emit ONLY structured JSON "
    "conforming to the schema — never code, never free-form prose outside the fields."
)


def compaction_user(source_records_json: str, dataset_summary: str, allowlist: list[str]) -> str:
    """Build the compaction prompt from the source experiment records (at/before trigger)."""

    return (
        f"Dataset: {dataset_summary}\n"
        f"Allowed models: {', '.join(allowlist)}.\n\n"
        "Source experiments so far (most recent last) — summarize ONLY these; you have no "
        "access to any later experiment:\n"
        f"{source_records_json}\n\n"
        "Produce the directional research memory: confirmed_findings, failed_directions, "
        "promising_directions, best_known_configs (model_name + hyperparameters + metric), "
        "unresolved_questions, a single next_step_recommendation, a confidence in [0,1], and "
        "a short rationale."
    )
