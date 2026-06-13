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


# --- feature 003 (T011): classifier allowlist + fixed-split metric-aware scoring -----

from ds_agent_loop import benchmark as B  # noqa: E402
from ds_agent_loop.prompts import TaskType  # noqa: E402


def test_classifier_allowlist_selected_by_task_type():
    assert train.allowlist_for(TaskType.classification) is train.CLASSIFIER_ALLOWLIST
    assert train.allowlist_for(TaskType.regression) is train.MODEL_ALLOWLIST
    assert "LogisticRegression" in train.CLASSIFIER_ALLOWLIST


def test_classifier_allowlist_rejects_a_regressor():
    with pytest.raises(train.ValidationRejected):
        train.validate_model_name("LinearRegression", train.CLASSIFIER_ALLOWLIST)


def test_regressor_allowlist_rejects_a_classifier():
    with pytest.raises(train.ValidationRejected):
        train.validate_model_name("LogisticRegression", train.MODEL_ALLOWLIST)


def test_score_on_split_regression_reports_rmse(tmp_path):
    d = B.get_descriptor("diabetes")
    df = B.load_dataset("diabetes")
    split = B.frozen_split("diabetes", state_dir=tmp_path)
    val, test = train.score_on_split(
        df, feature_schema=d.feature_schema, target=d.target, task_type=d.task_type,
        split=split, model_name="LinearRegression", hyperparameters={}, allowlist=train.allowlist_for(d.task_type),
    )
    assert "rmse" in val and "rmse" in test and test["rmse"] > 0


def test_score_on_split_classification_reports_macro_f1(tmp_path):
    d = B.get_descriptor("wine")
    df = B.load_dataset("wine")
    split = B.frozen_split("wine", state_dir=tmp_path)
    val, test = train.score_on_split(
        df, feature_schema=d.feature_schema, target=d.target, task_type=d.task_type,
        split=split, model_name="RandomForestClassifier", hyperparameters={"n_estimators": 25},
        allowlist=train.allowlist_for(d.task_type),
    )
    assert 0.0 <= test["macro_f1"] <= 1.0 and "accuracy" in test


def test_score_on_split_is_deterministic(tmp_path):
    d = B.get_descriptor("breast_cancer")
    df = B.load_dataset("breast_cancer")
    split = B.frozen_split("breast_cancer", state_dir=tmp_path)
    kw = dict(
        feature_schema=d.feature_schema, target=d.target, task_type=d.task_type, split=split,
        model_name="RandomForestClassifier", hyperparameters={"n_estimators": 15},
        allowlist=train.allowlist_for(d.task_type),
    )
    _, t1 = train.score_on_split(df, **kw)
    _, t2 = train.score_on_split(df, **kw)
    assert t1 == t2


def test_score_on_split_handles_categorical_one_hot(tmp_path):
    d = B.get_descriptor("delivery_time")
    df = B.load_dataset("delivery_time")
    split = B.frozen_split("delivery_time", state_dir=tmp_path)
    _, test = train.score_on_split(
        df, feature_schema=d.feature_schema, target=d.target, task_type=d.task_type,
        split=split, model_name="RandomForestRegressor", hyperparameters={},
        allowlist=train.allowlist_for(d.task_type),
    )
    assert test["rmse"] > 0  # traffic_level (categorical) one-hot encoded without error
