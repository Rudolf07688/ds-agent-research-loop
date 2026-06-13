"""Seed handling and local dataset expansion.

US1: bootstrap a seed sample + reusable ``data_spec`` (one LLM call) and persist both;
reuse existing valid state on later runs with no second call.

US2: expand the dataset toward a target size entirely in Python, deriving every row from
the saved ``data_spec`` (Constitution Principle V — no LLM call, no spec regeneration).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import ValidationError

import llm
from prompts import DataSpec, DeliveryRecord, Settings
from train import FEATURE_COLUMNS, TARGET_COLUMN

STATE_DIR = Path("state")
SEED_ROWS_FILE = "seed_rows.json"
DATA_SPEC_FILE = "data_spec.json"
DATASET_FILE = "dataset.csv"


class StateError(RuntimeError):
    """Raised when a required state file exists but cannot be read/parsed."""


# ---------------------------------------------------------------------------
# Load / persist seed state (US1)
# ---------------------------------------------------------------------------


def load_seed_state(
    state_dir: Path = STATE_DIR,
) -> tuple[list[DeliveryRecord], DataSpec] | None:
    """Return (seed_rows, data_spec) if both exist and are valid, else None.

    A present-but-corrupt file is an error (it must not be silently re-seeded over).
    """

    rows_path = state_dir / SEED_ROWS_FILE
    spec_path = state_dir / DATA_SPEC_FILE
    if not rows_path.exists() or not spec_path.exists():
        return None
    try:
        rows_raw = json.loads(rows_path.read_text())
        spec_raw = json.loads(spec_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(
            f"Corrupt seed state ({rows_path} / {spec_path}): {exc}"
        ) from exc
    try:
        rows = [DeliveryRecord.model_validate(r) for r in rows_raw]
        spec = DataSpec.model_validate(spec_raw)
    except ValidationError as exc:
        raise StateError(f"Invalid seed state failed validation: {exc}") from exc
    return rows, spec


def _persist_seed_state(
    rows: list[DeliveryRecord], spec: DataSpec, state_dir: Path
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / SEED_ROWS_FILE).write_text(
        json.dumps([r.model_dump() for r in rows], indent=2)
    )
    (state_dir / DATA_SPEC_FILE).write_text(json.dumps(spec.model_dump(), indent=2))


async def bootstrap_seed(
    settings: Settings, state_dir: Path = STATE_DIR
) -> tuple[list[DeliveryRecord], DataSpec]:
    """Return seed rows + spec, reusing valid state or generating once via the LLM."""

    existing = load_seed_state(state_dir)
    if existing is not None:
        return existing
    seed = await llm.generate_seed(settings)
    _persist_seed_state(seed.seed_rows, seed.data_spec, state_dir)
    return seed.seed_rows, seed.data_spec


# ---------------------------------------------------------------------------
# Local expansion from the saved spec (US2)
# ---------------------------------------------------------------------------


def load_data_spec(state_dir: Path = STATE_DIR) -> DataSpec:
    """Load the saved, immutable data spec."""

    spec_path = state_dir / DATA_SPEC_FILE
    try:
        return DataSpec.model_validate_json(spec_path.read_text())
    except (OSError, ValidationError) as exc:
        raise StateError(f"Cannot read data spec at {spec_path}: {exc}") from exc


def generate_rows(spec: DataSpec, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate ``n`` rows in pure Python from the saved spec.

    All feature ranges/categories come from the spec; the target is a fixed, readable
    function of the features plus spec-controlled noise. Every row satisfies the spec.
    """

    traffic_categories = spec.categories.get(
        "traffic_level", ["low", "medium", "high"]
    )
    traffic_weights = {"low": 1.0, "medium": 1.5, "high": 2.2}

    item_count = rng.integers(1, 6, size=n)
    distance_km = np.round(rng.uniform(0.5, 15.0, size=n), 2)
    traffic_level = rng.choice(traffic_categories, size=n)
    is_raining = rng.random(size=n) < 0.3
    hour_of_day = rng.integers(0, 24, size=n)

    # Readable, spec-anchored relationship for delivery time (minutes).
    base = 8.0
    traffic_factor = np.array([traffic_weights.get(t, 1.5) for t in traffic_level])
    rush_hour = np.isin(hour_of_day, [7, 8, 9, 17, 18, 19]).astype(float)
    target = (
        base
        + 2.5 * distance_km * traffic_factor
        + 1.5 * item_count
        + 6.0 * is_raining
        + 5.0 * rush_hour
    )
    noise = rng.normal(0.0, max(spec.noise_level, 0.0), size=n)
    delivery_time = np.clip(target + noise, 0.0, None)

    frame = pd.DataFrame(
        {
            "item_count": item_count.astype(int),
            "distance_km": distance_km.astype(float),
            "traffic_level": traffic_level,
            "is_raining": is_raining.astype(bool),
            "hour_of_day": hour_of_day.astype(int),
            TARGET_COLUMN: np.round(delivery_time, 2),
        }
    )
    return frame[FEATURE_COLUMNS + [TARGET_COLUMN]]


def expand_dataset(
    spec: DataSpec,
    target_size: int,
    seed_rows: list[DeliveryRecord] | None = None,
    state_dir: Path = STATE_DIR,
    seed: int = 0,
) -> pd.DataFrame:
    """Expand to ``target_size`` rows from the spec and persist ``dataset.csv``.

    Always anchored to the original saved spec; never regenerates the spec. Seed rows are
    kept as the first rows; the remainder is generated locally.
    """

    state_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = state_dir / DATASET_FILE

    seed_frame = pd.DataFrame()
    if seed_rows:
        seed_frame = pd.DataFrame([r.model_dump() for r in seed_rows])[
            FEATURE_COLUMNS + [TARGET_COLUMN]
        ]

    needed = max(0, target_size - len(seed_frame))
    rng = np.random.default_rng(seed)
    generated = generate_rows(spec, needed, rng) if needed > 0 else pd.DataFrame()

    dataset = pd.concat([seed_frame, generated], ignore_index=True)
    if len(dataset) > target_size:
        dataset = dataset.iloc[:target_size].reset_index(drop=True)

    dataset.to_csv(dataset_path, index=False)
    return dataset
