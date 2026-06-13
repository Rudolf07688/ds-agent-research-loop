"""Tests for decision dispatch/rejection (US4, T022) and stop conditions (US5, T026)."""

from __future__ import annotations

import asyncio

from ds_agent_loop import benchmark as B
from ds_agent_loop import main, provenance
from ds_agent_loop import store as S
from ds_agent_loop.prompts import (
    CellStatus,
    ExperimentCell,
    MemoryRegime,
    NextAction,
    NextStepDecision,
    Settings,
    TaskType,
)


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


# ===========================================================================
# Feature 004 — US4: the loop runs against any materialized member by id
# ===========================================================================


def _settings() -> Settings:
    return Settings(_env_file=None)


def _propose(model: str, action: NextAction = NextAction.keep_model, hp: dict | None = None):
    async def propose(settings, **kwargs):
        return NextStepDecision(action=action, model_name=model, hyperparameters=hp or {}, reason="x")
    return propose


def _run_member(store, dataset_id, *, propose, iterations=4, state_dir):
    descriptor, split, _ = B.load_member(store, dataset_id)
    return asyncio.run(
        main.run_cell(
            descriptor, MemoryRegime.recent_only, seed=0, k=3, m=10, iterations=iterations,
            store=store, settings=_settings(), state_dir=state_dir, split=split,
            propose=propose,
        )
    )


# --- T023 [US4]: regression vs classification member, allowlist + direction --


def test_loop_on_regression_member_uses_regressors_and_stops_at_budget(tmp_path):
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run_member(store, "diabetes", propose=_propose("RandomForestRegressor"), state_dir=tmp_path)
    assert cell.status is CellStatus.completed
    assert cell.last_iteration == 4  # ran the full budget
    assert cell.repro.get("stop_reason") == "budget"
    records = store.get_records(cell.cell_id)
    # direction-aware, lower-is-better regression metric reported on the frozen split
    assert all("rmse" in r.test_metrics for r in records)


def test_loop_on_classification_member_rejects_out_of_allowlist_before_training(tmp_path):
    store = S.FakeStore()
    B.materialize_suite(store, ["wine"])
    # proposing a regressor for a classification member is rejected before any training (US4)
    cell = _run_member(store, "wine", propose=_propose("RandomForestRegressor"), state_dir=tmp_path)
    assert cell.status is CellStatus.completed
    records = store.get_records(cell.cell_id)
    assert all("macro_f1" in r.test_metrics for r in records)  # higher-is-better classification
    # iterations 2..4 proposed an out-of-allowlist model -> rejected, baseline retained
    assert any(r.rejected for r in records[1:])
    assert all(r.model_name in B.CLASSIFIER_ALLOWLIST for r in records)


def test_loop_rejects_proposal_outside_frozen_action_space(tmp_path):
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    # expand_dataset is NOT in the frozen action space -> rejected before training (FR-016)
    cell = _run_member(
        store, "diabetes",
        propose=_propose("RandomForestRegressor", action=NextAction.expand_dataset),
        state_dir=tmp_path,
    )
    assert cell.status is CellStatus.completed
    records = store.get_records(cell.cell_id)
    assert any(r.rejected for r in records[1:])


# --- T024 [US4]: descriptor + split resolved from materialized suite ---------


def test_loop_resolves_member_from_materialized_suite_and_records_stop_reason(tmp_path):
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    descriptor, split, _ = B.load_member(store, "diabetes")
    # the loop is driven by the persisted descriptor + frozen split (not a file-only split)
    assert descriptor.task_type is TaskType.regression
    cell = _run_member(store, "diabetes", propose=_propose("RandomForestRegressor"), state_dir=tmp_path)
    # the frozen split the loop scored on is the materialized one
    assert split.content_hash == store.get_benchmark_split("diabetes", B.BENCHMARK_VERSION)["content_hash"]
    assert cell.repro.get("stop_reason") in ("budget", "agent_stop")


# ===========================================================================
# Feature 005 — US2 provenance, resume guard (FR-012), context-limit (FR-007)
# ===========================================================================


def test_every_decision_has_a_persisted_linked_view(tmp_path):
    """US2/SC-003: each iteration persists a hashed, correctly-keyed view linked from the record."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run_member(store, "diabetes", propose=_propose("RandomForestRegressor"), state_dir=tmp_path)
    records = store.get_records(cell.cell_id)
    views = {v.iteration: v for v in store.get_views(cell.cell_id)}
    assert set(views) == {r.iteration for r in records}  # one view per decision (T014)
    for r in records:
        v = views[r.iteration]
        assert v.cell_id == cell.cell_id and len(v.content_hash) == 64
        assert r.memory_view_ref == v.content_hash  # decision links its exact view (T013)


def test_resume_with_changed_regime_is_rejected(tmp_path):
    """FR-012/T029: a cell is one regime/k for life; a mismatched resume fails loudly."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    descriptor, split, _ = B.load_member(store, "diabetes")
    # Persist a running cell under recent_only, then attempt to drive the SAME cell_id under all_raw.
    cid = main.cell_id_for("diabetes", MemoryRegime.recent_only, 0, 3, 10)
    store.upsert_cell(
        ExperimentCell(cell_id=cid, dataset_id="diabetes", regime=MemoryRegime.all_raw,
                       seed=0, k=3, m=10, budget=4, status=CellStatus.running)
    )
    import pytest
    with pytest.raises(ValueError, match="controlled variable"):
        asyncio.run(main.run_cell(
            descriptor, MemoryRegime.recent_only, seed=0, k=3, m=10, iterations=4,
            store=store, settings=_settings(), state_dir=tmp_path, split=split,
            propose=_propose("RandomForestRegressor"),
        ))


def test_all_raw_context_limit_halts_and_records_context_limited(tmp_path):
    """FR-007 (G1): an all_raw view over the token limit halts the cell, never silently truncated."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    descriptor, split, _ = B.load_member(store, "diabetes")
    cell = asyncio.run(main.run_cell(
        descriptor, MemoryRegime.all_raw, seed=0, k=0, m=10, iterations=8,
        store=store, settings=_settings(), state_dir=tmp_path, split=split,
        propose=_propose("RandomForestRegressor"), context_token_limit=1,
    ))
    assert cell.status is CellStatus.context_limited
    assert cell.repro.get("stop_reason") == "context_limited"


# ===========================================================================
# Feature 006 — the compaction operator: recorded cadence, lineage, seam intact
# ===========================================================================


def _operator_compactor():
    """A hermetic stand-in for the real operator that emits a valid DirectionalMemory dict."""
    async def compactor(settings, *, source_records, descriptor):
        return {
            "confirmed_findings": [], "failed_directions": [], "promising_directions": [],
            "best_known_configs": [], "unresolved_questions": ["q"],
            "next_step_recommendation": "keep going", "confidence": 0.5,
            "rationale": f"compacted {len(source_records)} records",
        }
    return compactor


def _run_compacted(store, *, m, iterations, state_dir, k=3):
    descriptor, split, _ = B.load_member(store, "diabetes")
    return asyncio.run(
        main.run_cell(
            descriptor, MemoryRegime.compacted_recent, seed=0, k=k, m=m, iterations=iterations,
            store=store, settings=_settings(), state_dir=state_dir, split=split,
            propose=_propose("RandomForestRegressor"), compactor=_operator_compactor(),
        )
    )


def test_compacted_cell_records_cadence_and_trigger_mode_on_every_artifact(tmp_path):
    """FR-004/006a: every artifact records the cadence m and the trigger mode used."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run_compacted(store, m=3, iterations=9, state_dir=tmp_path)
    artifacts = store.get_artifacts(cell.cell_id)
    assert [a["trigger_iteration"] for a in artifacts] == [3, 6, 9]
    assert all(a["cadence"] == 3 for a in artifacts)
    assert all(a["trigger_mode"] == "fixed" for a in artifacts)


def test_rerunning_a_completed_trigger_yields_exactly_one_artifact(tmp_path):
    """SC-006: the (cell_id, trigger) upsert is idempotent — a resumed/re-run trigger never dups."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run_compacted(store, m=3, iterations=6, state_dir=tmp_path)
    before = store.get_artifacts(cell.cell_id)
    # Re-running a terminal cell is a no-op (resume guard) — artifacts remain exactly one per trigger.
    _run_compacted(store, m=3, iterations=6, state_dir=tmp_path)
    after = store.get_artifacts(cell.cell_id)
    assert [a["trigger_iteration"] for a in after] == [a["trigger_iteration"] for a in before] == [3, 6]


def test_artifact_lineage_is_exactly_records_at_or_before_trigger(tmp_path):
    """FR-005/007, SC-003: each artifact's source set == records with iteration <= trigger, no later."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run_compacted(store, m=3, iterations=9, state_dir=tmp_path)
    artifacts = store.get_artifacts(cell.cell_id)
    for art in artifacts:
        trigger = art["trigger_iteration"]
        expected = [r.iteration for r in store.get_records(cell.cell_id) if r.iteration <= trigger]
        assert sorted(art["source_record_ids"]) == expected
        assert max(art["source_record_ids"]) <= trigger  # no future leakage
    # ordered by trigger iteration
    assert [a["trigger_iteration"] for a in artifacts] == sorted(a["trigger_iteration"] for a in artifacts)


def test_operator_backed_compacted_cell_replays_unchanged(tmp_path):
    """FR-012/SC-005: a compacted_recent cell produced by the 006 operator replays 100% (005 seam)."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run_compacted(store, m=3, iterations=9, state_dir=tmp_path)
    result = provenance.verify_cell(store, cell.cell_id)
    assert result.ok and result.matched == result.total == cell.last_iteration


def test_operator_backed_compacted_cell_passes_cross_regime_audit(tmp_path):
    """FR-012/SC-005: an operator-backed compacted cell vs a recent_only cell differs only in memory."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    a = _run_compacted(store, m=3, iterations=6, state_dir=tmp_path)
    descriptor, split, _ = B.load_member(store, "diabetes")
    b = asyncio.run(main.run_cell(
        descriptor, MemoryRegime.recent_only, seed=0, k=3, m=10, iterations=6,
        store=store, settings=_settings(), state_dir=tmp_path, split=split,
        propose=_propose("RandomForestRegressor"),
    ))
    result = provenance.audit_regimes(store, a.cell_id, b.cell_id)
    assert result.ok and result.same_member_seed and result.fingerprint_equal
    assert result.differing_factor is None
