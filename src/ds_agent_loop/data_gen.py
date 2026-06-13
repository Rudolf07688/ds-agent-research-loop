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

from . import llm
from .prompts import DataSpec, DeliveryRecord, Settings
from .train import FEATURE_COLUMNS, TARGET_COLUMN

STATE_DIR = Path("state")
SEED_ROWS_FILE = "seed_rows.json"
DATA_SPEC_FILE = "data_spec.json"
DATASET_FILE = "dataset.csv"

# Append-only train/val/test partition files for the incremental synthetic dataset.
# Fractions are reused from the frozen benchmark suite so the split policy is single-sourced.
TRAIN_FILE = "train.csv"
VAL_FILE = "val.csv"
TEST_FILE = "test.csv"
SPLIT_FILES = {"train": TRAIN_FILE, "val": VAL_FILE, "test": TEST_FILE}


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


# ---------------------------------------------------------------------------
# Incremental, split-aware growth (60/20/20 train/val/test) — CLI-facing
# ---------------------------------------------------------------------------


def _split_counts(state_dir: Path) -> dict[str, int]:
    """Current row count (excluding header) of each append-only partition file."""

    counts: dict[str, int] = {}
    for name, fname in SPLIT_FILES.items():
        path = state_dir / fname
        if path.exists() and path.stat().st_size > 0:
            counts[name] = max(0, sum(1 for _ in path.open()) - 1)
        else:
            counts[name] = 0
    return counts


def add_records(
    count: int,
    *,
    spec: DataSpec | None = None,
    state_dir: Path = STATE_DIR,
    seed: int = 0,
) -> dict[str, int]:
    """Generate ``count`` fresh rows and append them, split 60/20/20, to train/val/test.

    Re-runnable: every invocation adds NEW rows on top of whatever already exists. A row
    keeps its partition forever (append-only) so there is no leakage and the growing dataset
    stays reproducible. Derives all rows from the saved ``data_spec`` in pure Python (no LLM,
    Principle V). The per-run RNG is offset by the existing total so repeated runs add distinct
    rows yet a fixed ``seed`` + starting state reproduces the exact same sequence.
    """

    # Import here to avoid pulling sklearn (a benchmark dependency) on the hot data-gen path.
    from .benchmark import TRAIN_FRAC, VAL_FRAC

    if count <= 0:
        raise ValueError(f"count must be positive, got {count}.")
    if spec is None:
        spec = load_data_spec(state_dir)

    state_dir.mkdir(parents=True, exist_ok=True)
    offset = sum(_split_counts(state_dir).values())
    rng = np.random.default_rng(seed + offset)

    rows = generate_rows(spec, count, rng)
    perm = rng.permutation(count)
    n_train = int(round(TRAIN_FRAC * count))
    n_val = int(round(VAL_FRAC * count))
    parts = {
        "train": perm[:n_train],
        "val": perm[n_train : n_train + n_val],
        "test": perm[n_train + n_val :],
    }

    added: dict[str, int] = {}
    for name, idx in parts.items():
        chunk = rows.iloc[sorted(int(i) for i in idx)].reset_index(drop=True)
        path = state_dir / SPLIT_FILES[name]
        write_header = not path.exists() or path.stat().st_size == 0
        chunk.to_csv(path, mode="a", header=write_header, index=False)
        added[name] = len(chunk)
    return added


def data_status(state_dir: Path = STATE_DIR) -> dict[str, object]:
    """Return per-partition counts, total, and realized fractions for the split files."""

    counts = _split_counts(state_dir)
    total = sum(counts.values())
    fractions = {
        name: (counts[name] / total if total else 0.0) for name in SPLIT_FILES
    }
    return {"counts": counts, "total": total, "fractions": fractions}


# ---------------------------------------------------------------------------
# CLI: `ds-agent-data {bootstrap,add,status}`
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        prog="ds-agent-data",
        description="Grow the synthetic dataset incrementally with a 60/20/20 "
        "train/val/test split (append-only).",
    )
    parser.add_argument(
        "--state-dir",
        default=str(STATE_DIR),
        help=f"directory holding seed + split files (default: {STATE_DIR})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "bootstrap",
        help="seed the dataset spec once via the LLM (reuses valid state if present)",
    )

    add = sub.add_parser("add", help="generate N new rows and append them, split 60/20/20")
    add.add_argument("--count", "-n", type=int, required=True, help="number of rows to add")
    add.add_argument("--seed", type=int, default=0, help="base RNG seed (default: 0)")

    sub.add_parser("status", help="show per-partition counts and realized fractions")

    args = parser.parse_args()
    state_dir = Path(args.state_dir)

    if args.command == "bootstrap":
        asyncio.run(bootstrap_seed(Settings(), state_dir))
        print(f"Seed + data_spec ready in {state_dir}/.")
        return

    if args.command == "add":
        try:
            added = add_records(args.count, state_dir=state_dir, seed=args.seed)
        except StateError as exc:
            raise SystemExit(
                f"{exc}\nRun `ds-agent-data --state-dir {state_dir} bootstrap` first."
            ) from exc
        status = data_status(state_dir)
        print(
            f"Added {sum(added.values())} rows "
            f"(train +{added['train']}, val +{added['val']}, test +{added['test']})."
        )
        counts = status["counts"]
        fr = status["fractions"]
        print(
            f"Totals: train={counts['train']} ({fr['train']:.0%}), "
            f"val={counts['val']} ({fr['val']:.0%}), "
            f"test={counts['test']} ({fr['test']:.0%}) — {status['total']} rows."
        )
        return

    if args.command == "status":
        status = data_status(state_dir)
        counts = status["counts"]
        fr = status["fractions"]
        if not status["total"]:
            print(f"No split files in {state_dir}/ yet. Run `add --count N` to start.")
            return
        for name in ("train", "val", "test"):
            print(f"{name:5s}: {counts[name]:>7d} rows  ({fr[name]:.1%})")
        print(f"total: {status['total']:>7d} rows")


if __name__ == "__main__":
    main()
