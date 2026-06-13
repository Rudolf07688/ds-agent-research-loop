"""Feature prep, the model allowlist, hyperparameter validation, training, scoring.

Python is the sole authority on what runs (Constitution Principle III): the LLM may only
name a model from ``MODEL_ALLOWLIST`` and propose JSON hyperparameters, all of which are
validated here before any estimator is constructed or trained.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .prompts import NextAction, NextStepDecision

# Fixed set of approved regressors the LLM may choose from. Anything else is rejected.
MODEL_ALLOWLIST: dict[str, type] = {
    "LinearRegression": LinearRegression,
    "RandomForestRegressor": RandomForestRegressor,
    "GradientBoostingRegressor": GradientBoostingRegressor,
    "HistGradientBoostingRegressor": HistGradientBoostingRegressor,
}

# The first-iteration baseline (FR-005a).
BASELINE_MODEL = "LinearRegression"

# Dataset columns (the task is fixed; see the constitution Scope section).
TARGET_COLUMN = "delivery_time_minutes"
NUMERIC_FEATURES = ["item_count", "distance_km", "is_raining", "hour_of_day"]
CATEGORICAL_FEATURES = ["traffic_level"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Fixed random seed for reproducible scoring (Principle IV).
RANDOM_SEED = 42


class ValidationRejected(ValueError):
    """Raised when a proposed model/hyperparameter set is outside the safe bounds."""


# ---------------------------------------------------------------------------
# Validation (Principle III) — the safety boundary, runs before any training
# ---------------------------------------------------------------------------


def validate_model_name(model_name: str) -> type:
    """Return the estimator class for an allowlisted model, else reject."""

    if model_name not in MODEL_ALLOWLIST:
        raise ValidationRejected(
            f"Model '{model_name}' is not on the allowlist "
            f"{sorted(MODEL_ALLOWLIST)}."
        )
    return MODEL_ALLOWLIST[model_name]


def validate_hyperparameters(
    model_name: str, hyperparameters: dict[str, Any]
) -> dict[str, Any]:
    """Reject unknown/invalid hyperparameters; return the validated set."""

    cls = validate_model_name(model_name)
    valid_keys = set(cls().get_params().keys())
    unknown = set(hyperparameters) - valid_keys
    if unknown:
        raise ValidationRejected(
            f"Unknown hyperparameters for {model_name}: {sorted(unknown)}."
        )
    try:
        estimator = cls(**hyperparameters)
        # scikit-learn checks parameter *values* at fit time; trigger that check now so
        # invalid values are rejected before any training (Principle III).
        estimator._validate_params()
    except Exception as exc:  # invalid types/values for this estimator
        raise ValidationRejected(
            f"Invalid hyperparameters for {model_name}: {exc}"
        ) from exc
    return dict(hyperparameters)


def validate_decision(decision: NextStepDecision, current_model: str) -> None:
    """Validate a next-step decision against the safe bounds (US4).

    ``action`` is already an enum (Pydantic). For model-bearing actions the model must be
    allowlisted; for any action that will train, the hyperparameters must validate against
    the model that will be used. Never inspects/executes free-form content.
    """

    action = decision.action
    if action in (NextAction.keep_model, NextAction.switch_model):
        validate_model_name(decision.model_name)
    if action in (
        NextAction.keep_model,
        NextAction.switch_model,
        NextAction.tune_hyperparameters,
    ):
        target_model = decision.model_name or current_model
        validate_hyperparameters(target_model, decision.hyperparameters)


# ---------------------------------------------------------------------------
# Estimator construction + scoring
# ---------------------------------------------------------------------------


def build_estimator(model_name: str, hyperparameters: dict[str, Any]) -> Pipeline:
    """Build a one-hot + estimator pipeline from a validated model + hyperparameters."""

    cls = validate_model_name(model_name)
    params = validate_hyperparameters(model_name, hyperparameters)
    if "random_state" in cls().get_params() and "random_state" not in params:
        params["random_state"] = RANDOM_SEED
    estimator = cls(**params)
    preprocess = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES)],
        remainder="passthrough",
    )
    return Pipeline([("pre", preprocess), ("model", estimator)])


def score_model(
    dataset: pd.DataFrame, model_name: str, hyperparameters: dict[str, Any]
) -> dict[str, float]:
    """5-fold CV score; primary RMSE, with R² and MAE as secondary metrics."""

    features = dataset[FEATURE_COLUMNS]
    target = dataset[TARGET_COLUMN]
    estimator = build_estimator(model_name, hyperparameters)
    cv = KFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    scoring = {
        "rmse": "neg_root_mean_squared_error",
        "r2": "r2",
        "mae": "neg_mean_absolute_error",
    }
    results = cross_validate(estimator, features, target, cv=cv, scoring=scoring)
    return {
        "rmse": float(-results["test_rmse"].mean()),
        "r2": float(results["test_r2"].mean()),
        "mae": float(-results["test_mae"].mean()),
    }
