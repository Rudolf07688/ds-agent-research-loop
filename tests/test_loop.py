"""Tests for decision dispatch/rejection (US4, T022) and stop conditions (US5, T026)."""

from __future__ import annotations

import main
from prompts import NextAction, NextStepDecision


# --- US4: T022 — rejection retains the prior model --------------------------


def test_rejected_proposal_is_skipped_and_prior_model_retained():
    bad = NextStepDecision(
        action=NextAction.switch_model,
        model_name="NotAllowedModel",
        hyperparameters={},
        reason="try something exotic",
    )
    plan, rejected, reason = main.decide_next(
        bad, current_model="LinearRegression", current_hp={"fit_intercept": True}, current_size=500
    )
    assert rejected
    assert plan.model_name == "LinearRegression"
    assert plan.hyperparameters == {"fit_intercept": True}
    assert "allowlist" in reason.lower()


def test_rejected_bad_hyperparameters_retains_prior_model():
    bad = NextStepDecision(
        action=NextAction.tune_hyperparameters,
        model_name="RandomForestRegressor",
        hyperparameters={"n_estimators": -10},
        reason="negative trees",
    )
    plan, rejected, _ = main.decide_next(
        bad, current_model="RandomForestRegressor", current_hp={}, current_size=500
    )
    assert rejected and plan.model_name == "RandomForestRegressor"


def test_valid_switch_model_is_applied():
    good = NextStepDecision(
        action=NextAction.switch_model,
        model_name="RandomForestRegressor",
        hyperparameters={"n_estimators": 50},
        reason="more capacity",
    )
    plan, rejected, _ = main.decide_next(
        good, current_model="LinearRegression", current_hp={}, current_size=500
    )
    assert not rejected
    assert plan.model_name == "RandomForestRegressor"
    assert plan.hyperparameters == {"n_estimators": 50}


def test_expand_dataset_plans_more_rows():
    decision = NextStepDecision(
        action=NextAction.expand_dataset, model_name="", hyperparameters={}, reason="more data"
    )
    plan, rejected, _ = main.decide_next(
        decision, current_model="LinearRegression", current_hp={}, current_size=500
    )
    assert not rejected and plan.expand_to == 500 + main.EXPAND_STEP


def test_stop_action_sets_stop():
    decision = NextStepDecision(
        action=NextAction.stop, model_name="", hyperparameters={}, reason="good enough"
    )
    plan, rejected, _ = main.decide_next(
        decision, current_model="LinearRegression", current_hp={}, current_size=500
    )
    assert not rejected and plan.stop


# --- US5: T026 — stop conditions -------------------------------------------


def test_stops_after_patience_rounds_without_improvement():
    assert main.should_stop(no_improvement_rounds=3, patience=3)
    assert main.should_stop(no_improvement_rounds=4, patience=3)


def test_continues_when_within_patience():
    assert not main.should_stop(no_improvement_rounds=2, patience=3)
    assert not main.should_stop(no_improvement_rounds=0, patience=3)
