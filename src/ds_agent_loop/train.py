"""Feature prep, the model allowlist, hyperparameter validation, training, scoring.

Python is the sole authority on what runs (Constitution Principle III): the LLM may only
name a model from ``MODEL_ALLOWLIST`` and propose JSON hyperparameters, all of which are
validated here before any estimator is constructed or trained.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import KFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .prompts import NextAction, NextStepDecision, TaskType

# Fixed set of approved regressors the LLM may choose from. Anything else is rejected.
MODEL_ALLOWLIST: dict[str, type] = {
    "LinearRegression": LinearRegression,
    "RandomForestRegressor": RandomForestRegressor,
    "GradientBoostingRegressor": GradientBoostingRegressor,
    "HistGradientBoostingRegressor": HistGradientBoostingRegressor,
}

# Fixed set of approved classifiers (v5.0.0 Principle III widens the allowlist to
# classifiers; still fixed, finite, developer-owned). Selected by dataset task type.
CLASSIFIER_ALLOWLIST: dict[str, type] = {
    "LogisticRegression": LogisticRegression,
    "RandomForestClassifier": RandomForestClassifier,
    "GradientBoostingClassifier": GradientBoostingClassifier,
    "HistGradientBoostingClassifier": HistGradientBoostingClassifier,
}

# The first-iteration baseline (FR-005a) — per task type.
BASELINE_MODEL = "LinearRegression"
BASELINE_BY_TASK: dict[TaskType, str] = {
    TaskType.regression: "LinearRegression",
    TaskType.classification: "LogisticRegression",
}


def allowlist_for(task_type: TaskType) -> dict[str, type]:
    """Return the fixed allowlist for a task type (regressors vs classifiers)."""

    return MODEL_ALLOWLIST if task_type is TaskType.regression else CLASSIFIER_ALLOWLIST

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


def validate_model_name(model_name: str, allowlist: dict[str, type] | None = None) -> type:
    """Return the estimator class for an allowlisted model, else reject.

    ``allowlist`` defaults to the regressor ``MODEL_ALLOWLIST`` for backward compatibility;
    the ablation passes the task-appropriate allowlist (``allowlist_for(task_type)``).
    """

    allowlist = allowlist or MODEL_ALLOWLIST
    if model_name not in allowlist:
        raise ValidationRejected(
            f"Model '{model_name}' is not on the allowlist {sorted(allowlist)}."
        )
    return allowlist[model_name]


def validate_hyperparameters(
    model_name: str, hyperparameters: dict[str, Any], allowlist: dict[str, type] | None = None
) -> dict[str, Any]:
    """Reject unknown/invalid hyperparameters; return the validated set."""

    cls = validate_model_name(model_name, allowlist)
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


def validate_decision(
    decision: NextStepDecision, current_model: str, allowlist: dict[str, type] | None = None
) -> None:
    """Validate a next-step decision against the safe bounds (US4).

    ``action`` is already an enum (Pydantic). For model-bearing actions the model must be
    allowlisted; for any action that will train, the hyperparameters must validate against
    the model that will be used. Never inspects/executes free-form content.
    """

    action = decision.action
    if action in (NextAction.keep_model, NextAction.switch_model):
        validate_model_name(decision.model_name, allowlist)
    if action in (
        NextAction.keep_model,
        NextAction.switch_model,
        NextAction.tune_hyperparameters,
    ):
        target_model = decision.model_name or current_model
        validate_hyperparameters(target_model, decision.hyperparameters, allowlist)


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


# ---------------------------------------------------------------------------
# Generic, descriptor-driven scoring on FIXED train/val/test splits (feature 003)
# ---------------------------------------------------------------------------
#
# Decision 6: fit on train, select/early-accept on validation, report the frozen test
# metric for the primary outcome (FR-019). Metric-aware and direction-correct (FR-023).


def build_pipeline(
    feature_schema: dict[str, str],
    model_name: str,
    hyperparameters: dict[str, Any],
    allowlist: dict[str, type],
) -> Pipeline:
    """One-hot (declared categoricals) + validated estimator, generic over any dataset."""

    cls = validate_model_name(model_name, allowlist)
    params = validate_hyperparameters(model_name, hyperparameters, allowlist)
    if "random_state" in cls().get_params() and "random_state" not in params:
        params["random_state"] = RANDOM_SEED
    estimator = cls(**params)
    categoricals = [c for c, kind in feature_schema.items() if kind == "categorical"]
    if categoricals:
        preprocess = ColumnTransformer(
            [("cat", OneHotEncoder(handle_unknown="ignore"), categoricals)],
            remainder="passthrough",
        )
        return Pipeline([("pre", preprocess), ("model", estimator)])
    return Pipeline([("model", estimator)])


def compute_metrics(task_type: TaskType, y_true, y_pred) -> dict[str, float]:
    """Metric-aware scoring. Regression: rmse(primary)/mae/r2. Classification:
    macro_f1(primary)/accuracy. The primary metric is named per the descriptor."""

    if task_type is TaskType.regression:
        return {
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "r2": float(r2_score(y_true, y_pred)),
        }
    return {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }


def score_on_split(
    dataset: pd.DataFrame,
    *,
    feature_schema: dict[str, str],
    target: str,
    task_type: TaskType,
    split: dict[str, list[int]],
    model_name: str,
    hyperparameters: dict[str, Any],
    allowlist: dict[str, type],
) -> tuple[dict[str, float], dict[str, float]]:
    """Fit on the frozen train split, return ``(val_metrics, test_metrics)`` (Decision 6).

    The split is reused identically across regimes/seeds so the comparison is paired and
    fair (SC-002); only deterministic training varies with the model/hyperparameters.
    """

    features = list(feature_schema)
    X = dataset[features]
    y = dataset[target]
    Xtr, ytr = X.iloc[split["train"]], y.iloc[split["train"]]
    pipeline = build_pipeline(feature_schema, model_name, hyperparameters, allowlist)
    pipeline.fit(Xtr, ytr)
    val_metrics = compute_metrics(task_type, y.iloc[split["val"]], pipeline.predict(X.iloc[split["val"]]))
    test_metrics = compute_metrics(task_type, y.iloc[split["test"]], pipeline.predict(X.iloc[split["test"]]))
    return val_metrics, test_metrics
