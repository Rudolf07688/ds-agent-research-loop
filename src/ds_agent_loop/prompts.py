"""Typed entities, centralized settings, JSON schemas, and prompt text.

This module is the single home for the project's Pydantic models (Constitution
Principle VIII), the one ``pydantic-settings`` configuration object, the two sanctioned
LLM JSON schemas (Principle II), and the prompt templates that drive the two LLM calls.
Keeping these together honours the fixed flat module list (no extra ``config.py``).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class RunRecord(BaseModel):
    """One iteration's outcome; appended to history."""

    model_config = ConfigDict(extra="forbid")

    iteration: int
    dataset_size: int
    model_name: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float]
    rationale: str
    timestamp: str


# ---------------------------------------------------------------------------
# Centralized settings (the single pydantic-settings object) — Principle VIII
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Single source of truth for runtime config; loaded from ``.env``/environment.

    CLI flags override these at call time (see ``main.py``). Field names map to
    upper-case environment variables (e.g. ``llm_api_key`` -> ``LLM_API_KEY``).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None

    n_iterations: int = 10
    patience: int = 3
    target_size: int = 500
    primary_metric: str = "rmse"


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
