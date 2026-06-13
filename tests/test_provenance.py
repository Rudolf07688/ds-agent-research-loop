"""Feature 005 — decision-provenance verification (US3/US4/US5).

Verified replay (T018-T020), config fingerprint + cross-regime audit (T023-T025), and export
round-trip / Alembic-ownership (T027-T028). All offline via FakeStore; replay/audit make no LLM
calls (Principle IX)."""

from __future__ import annotations

import asyncio
import json

from ds_agent_loop import benchmark as B
from ds_agent_loop import main, provenance
from ds_agent_loop import store as S
from ds_agent_loop.prompts import MemoryRegime, NextAction, NextStepDecision, Settings


def _settings() -> Settings:
    return Settings(_env_file=None)


def _propose(model: str, action: NextAction = NextAction.keep_model):
    async def propose(settings, **kwargs):
        return NextStepDecision(action=action, model_name=model, hyperparameters={}, reason="x")
    return propose


def _run(store, dataset_id, regime, *, seed=0, k=3, iterations=4, state_dir, model="RandomForestRegressor"):
    descriptor, split, _ = B.load_member(store, dataset_id)
    return asyncio.run(
        main.run_cell(
            descriptor, regime, seed=seed, k=k, m=10, iterations=iterations,
            store=store, settings=_settings(), state_dir=state_dir, split=split,
            propose=_propose(model),
        )
    )


# --- US3: verified replay (T018-T020) ---------------------------------------


def test_verify_cell_matches_every_decision_across_regimes(tmp_path):
    """SC-004: a clean run replays 100% under each regime, with no LLM calls."""
    for regime in MemoryRegime:
        store = S.FakeStore()
        B.materialize_suite(store, ["diabetes"])
        cell = _run(store, "diabetes", regime, state_dir=tmp_path)
        result = provenance.verify_cell(store, cell.cell_id)
        assert result.total == cell.last_iteration
        assert result.ok, f"{regime.value} mismatches: {result.mismatches}"
        assert result.matched == result.total


def test_verify_cell_detects_a_tampered_view(tmp_path):
    """FR-009: a corrupted persisted view fails replay loudly, naming the iteration."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run(store, "diabetes", MemoryRegime.all_raw, state_dir=tmp_path)
    # Tamper the record link for iteration 3 so the rebuilt hash no longer matches.
    rec = store.get_records(cell.cell_id)[2]
    store.append_record(rec.model_copy(update={"memory_view_ref": "deadbeef"}))
    result = provenance.verify_cell(store, cell.cell_id)
    assert not result.ok
    assert [m.iteration for m in result.mismatches] == [3]
    assert result.mismatches[0].expected_hash == "deadbeef"


def test_empty_history_and_k_over_history_replay_identically(tmp_path):
    """FR-013/SC-006: the empty-history first decision and k>history clamp are replayable."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    # k larger than the whole run so recent_only always clamps to available history.
    cell = _run(store, "diabetes", MemoryRegime.recent_only, k=99, iterations=3, state_dir=tmp_path)
    result = provenance.verify_cell(store, cell.cell_id)
    assert result.ok and result.total == 3


# --- US4: config fingerprint + cross-regime audit (T023-T025) ---------------


def test_audit_two_regimes_same_member_seed_is_clean(tmp_path):
    """SC-005: two regimes over one (member, seed) share a fingerprint; regime is the difference."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    a = _run(store, "diabetes", MemoryRegime.recent_only, k=3, state_dir=tmp_path)
    b = _run(store, "diabetes", MemoryRegime.all_raw, k=0, state_dir=tmp_path)
    result = provenance.audit_regimes(store, a.cell_id, b.cell_id)
    assert result.ok
    assert result.same_member_seed and result.fingerprint_equal
    assert result.differing_factor is None
    assert "recent_only -> all_raw" in result.differing_dimension


def test_audit_flags_a_contaminating_held_fixed_factor(tmp_path):
    """FR-011: a differing held-fixed factor (budget) fails the audit, naming the factor."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    a = _run(store, "diabetes", MemoryRegime.recent_only, iterations=4, state_dir=tmp_path)
    b = _run(store, "diabetes", MemoryRegime.all_raw, iterations=6, state_dir=tmp_path)
    result = provenance.audit_regimes(store, a.cell_id, b.cell_id)
    assert not result.ok
    assert result.same_member_seed and not result.fingerprint_equal
    assert result.differing_factor == "budget"


def test_audit_rejects_different_member_or_seed(tmp_path):
    """FR-011 gate: cells of different members are not a memory-only comparison."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes", "wine"])
    a = _run(store, "diabetes", MemoryRegime.recent_only, state_dir=tmp_path)
    b = _run(store, "wine", MemoryRegime.recent_only, model="RandomForestClassifier", state_dir=tmp_path)
    result = provenance.audit_regimes(store, a.cell_id, b.cell_id)
    assert not result.ok and not result.same_member_seed
    assert "not a memory-only comparison" in result.reason


def test_config_fingerprint_excludes_regime_and_k(tmp_path):
    """FR-010: fingerprint is identical across regimes/k for a fixed (member, seed)."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    a = _run(store, "diabetes", MemoryRegime.recent_only, k=3, state_dir=tmp_path)
    b = _run(store, "diabetes", MemoryRegime.compacted_recent, k=7, state_dir=tmp_path)
    assert a.repro["config_fingerprint"] == b.repro["config_fingerprint"]


# --- US5: export round-trip + Alembic ownership (T027-T028) ------------------


def test_memory_views_export_round_trips_byte_identically(tmp_path):
    """SC-007: exported memory_views.json reloads to byte-identical view data."""
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    cell = _run(store, "diabetes", MemoryRegime.all_raw, state_dir=tmp_path)
    out = S.export(store, tmp_path / "exp")
    exported = json.loads((out / S._safe_dir(cell.cell_id) / "memory_views.json").read_text())
    live = [v.model_dump(mode="json") for v in store.get_views(cell.cell_id)]
    assert exported == live
    # the fingerprint is carried in the export index (cells.csv)
    assert "config_fingerprint" in (out / "cells.csv").read_text()


def test_no_operational_create_all_or_adhoc_ddl_added(tmp_path):
    """FR-014/Principle IV: this feature adds no operational create_all; schema is Alembic-owned."""
    src = (
        __import__("pathlib").Path(provenance.__file__).parent / "provenance.py"
    ).read_text()
    assert "create_all" not in src
    assert "CREATE TABLE" not in src.upper()
