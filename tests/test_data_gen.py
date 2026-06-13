"""Tests for seed bootstrap (US1) and local expansion (US2)."""

from __future__ import annotations

import asyncio
import json

import pytest

from ds_agent_loop import data_gen
from ds_agent_loop.prompts import DataSpec, DeliveryRecord, Settings

SPEC = DataSpec(
    features=["item_count", "distance_km", "traffic_level", "is_raining", "hour_of_day"],
    target="delivery_time_minutes",
    rules=["delivery time grows with distance and traffic"],
    categories={"traffic_level": ["low", "medium", "high"]},
    noise_level=2.0,
)

SEED_ROWS = [
    DeliveryRecord(
        item_count=2,
        distance_km=3.5,
        traffic_level="low",
        is_raining=False,
        hour_of_day=12,
        delivery_time_minutes=22.0,
    ),
    DeliveryRecord(
        item_count=4,
        distance_km=8.0,
        traffic_level="high",
        is_raining=True,
        hour_of_day=18,
        delivery_time_minutes=55.0,
    ),
]


def _write_state(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / data_gen.SEED_ROWS_FILE).write_text(
        json.dumps([r.model_dump() for r in SEED_ROWS])
    )
    (state_dir / data_gen.DATA_SPEC_FILE).write_text(json.dumps(SPEC.model_dump()))


# --- US1: T008 -------------------------------------------------------------


def test_bootstrap_skips_generation_when_valid_state_exists(tmp_path, monkeypatch):
    _write_state(tmp_path)

    async def _fail(_settings):
        raise AssertionError("LLM seed generation must not be called when state exists")

    monkeypatch.setattr(data_gen.llm, "generate_seed", _fail)

    rows, spec = asyncio.run(
        data_gen.bootstrap_seed(Settings(), state_dir=tmp_path)
    )

    assert spec.target == "delivery_time_minutes"
    assert len(rows) == len(SEED_ROWS)


def test_corrupt_seed_state_raises(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / data_gen.SEED_ROWS_FILE).write_text("{ not json")
    (tmp_path / data_gen.DATA_SPEC_FILE).write_text(json.dumps(SPEC.model_dump()))

    with pytest.raises(data_gen.StateError):
        data_gen.load_seed_state(state_dir=tmp_path)


# --- US2: T012 -------------------------------------------------------------


def test_expansion_uses_only_spec_and_satisfies_ranges(tmp_path):
    target = 300
    dataset = data_gen.expand_dataset(
        SPEC, target_size=target, seed_rows=SEED_ROWS, state_dir=tmp_path, seed=7
    )

    assert len(dataset) == target
    assert (tmp_path / data_gen.DATASET_FILE).exists()

    # Every row satisfies the spec's categories and basic ranges.
    assert set(dataset["traffic_level"]).issubset(set(SPEC.categories["traffic_level"]))
    assert (dataset["item_count"] >= 1).all()
    assert (dataset["distance_km"] >= 0).all()
    assert dataset["hour_of_day"].between(0, 23).all()
    assert (dataset["delivery_time_minutes"] >= 0).all()


def test_expansion_is_deterministic_for_a_fixed_seed(tmp_path):
    a = data_gen.expand_dataset(
        SPEC, target_size=100, seed_rows=SEED_ROWS, state_dir=tmp_path / "a", seed=1
    )
    b = data_gen.expand_dataset(
        SPEC, target_size=100, seed_rows=SEED_ROWS, state_dir=tmp_path / "b", seed=1
    )
    assert a.equals(b)
