"""Tests for the model allowlist + hyperparameter validation (US3, T015)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ds_agent_loop import train
from ds_agent_loop.prompts import NextAction, NextStepDecision
from ds_agent_loop.train import FEATURE_COLUMNS, TARGET_COLUMN


def _toy_dataset(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        {
            "item_count": rng.integers(1, 5, n),
            "distance_km": rng.uniform(0.5, 12, n).round(2),
            "is_raining": rng.random(n) < 0.3,
            "hour_of_day": rng.integers(0, 24, n),
            "traffic_level": rng.choice(["low", "medium", "high"], n),
        }
    )
    frame[TARGET_COLUMN] = (
        5 + 2 * frame["distance_km"] + 1.5 * frame["item_count"]
    ).round(2)
    return frame[FEATURE_COLUMNS + [TARGET_COLUMN]]


def test_out_of_allowlist_model_is_rejected():
    with pytest.raises(train.ValidationRejected):
        train.validate_model_name("MaliciousModel")


def test_unknown_hyperparameter_is_rejected():
    with pytest.raises(train.ValidationRejected):
        train.validate_hyperparameters("RandomForestRegressor", {"not_a_param": 5})


def test_invalid_hyperparameter_value_is_rejected():
    with pytest.raises(train.ValidationRejected):
        train.validate_hyperparameters("RandomForestRegressor", {"n_estimators": -3})


def test_valid_model_and_hyperparameters_accepted():
    params = train.validate_hyperparameters(
        "RandomForestRegressor", {"n_estimators": 10}
    )
    assert params == {"n_estimators": 10}


def test_decision_with_code_bearing_model_name_is_rejected():
    decision = NextStepDecision(
        action=NextAction.switch_model,
        model_name="__import__('os').system('rm -rf /')",
        hyperparameters={},
        reason="malicious",
    )
    with pytest.raises(train.ValidationRejected):
        train.validate_decision(decision, current_model="LinearRegression")


def test_score_model_returns_rmse():
    metrics = train.score_model(_toy_dataset(), "LinearRegression", {})
    assert "rmse" in metrics and metrics["rmse"] >= 0
    assert "r2" in metrics and "mae" in metrics
