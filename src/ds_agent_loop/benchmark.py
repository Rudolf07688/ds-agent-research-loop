"""The versioned benchmark suite + frozen train/val/test splits (Principle V).

A fixed, versioned suite of small tabular datasets — regression AND classification — each
with one pre-registered primary metric and a frozen train/validation/test split reused
byte-for-byte across every regime, seed, ``k`` and ``m`` (FR-016/017, SC-002). The split
depends ONLY on the dataset (a fixed split seed), never on the cell seed, so the only thing
that ever differs across a paired comparison is the memory regime.

v1 ships five datasets that load fully offline from scikit-learn's bundled data and a
locally-generated synthetic task (zero network, deterministic — keeps the sweep and the
test suite hermetic). ``california_housing`` is available as an optional fetch-and-cache
extra but is NOT in the default suite, so a default run never touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sklearn.datasets import (
    load_breast_cancer,
    load_diabetes,
    load_iris,
    load_wine,
)

from .prompts import TaskType

BENCHMARK_VERSION = "v1"

# Fixed split seed — fixed across the whole suite so splits are reproducible and
# independent of the cell seed (Principle V, SC-002).
SPLIT_SEED = 20260613
TRAIN_FRAC = 0.6
VAL_FRAC = 0.2  # remainder (0.2) is test


class DatasetDescriptor(BaseModel):
    """Metadata for one benchmark task (data-model.md §DatasetDescriptor).

    The loader is resolved by ``dataset_id`` (see ``_LOADERS``) rather than carried on the
    model, so the descriptor stays fully typed and JSON-serialisable for repro/export.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    task_type: TaskType
    feature_schema: dict[str, str]  # column -> "numeric" | "categorical"
    target: str
    primary_metric: str  # "rmse" (regression) | "macro_f1" (classification)
    metric_direction: int  # +1 higher-is-better, -1 lower-is-better (FR-023)
    split_ref: str
    benchmark_version: str = BENCHMARK_VERSION
    feature_names: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Loaders (all offline + deterministic)
# ---------------------------------------------------------------------------


def _make_delivery_time(n: int = 600) -> pd.DataFrame:
    """Deterministically generate the synthetic delivery-time task locally (no LLM).

    The anchored relationship (Principle V): delivery time grows with item count,
    distance, traffic, rain and rush hours, plus small fixed-seed noise.
    """

    rng = np.random.default_rng(SPLIT_SEED)
    item_count = rng.integers(1, 11, size=n)
    distance_km = np.round(rng.uniform(0.5, 20.0, size=n), 2)
    traffic_level = rng.choice(["low", "medium", "high"], size=n, p=[0.4, 0.4, 0.2])
    is_raining = rng.integers(0, 2, size=n)
    hour_of_day = rng.integers(0, 24, size=n)

    traffic_factor = np.select(
        [traffic_level == "low", traffic_level == "medium", traffic_level == "high"],
        [1.0, 1.4, 1.9],
    )
    rush = ((hour_of_day >= 7) & (hour_of_day <= 9)) | ((hour_of_day >= 16) & (hour_of_day <= 19))
    base = (
        8.0
        + 1.5 * item_count
        + 1.2 * distance_km * traffic_factor
        + 6.0 * is_raining
        + 5.0 * rush.astype(float)
    )
    noise = rng.normal(0.0, 2.0, size=n)
    delivery_time_minutes = np.round(np.maximum(base + noise, 1.0), 2)

    return pd.DataFrame(
        {
            "item_count": item_count,
            "distance_km": distance_km,
            "traffic_level": traffic_level,
            "is_raining": is_raining,
            "hour_of_day": hour_of_day,
            "delivery_time_minutes": delivery_time_minutes,
        }
    )


def _sklearn_frame(loader, target_name: str) -> pd.DataFrame:
    bunch = loader()
    df = pd.DataFrame(bunch.data, columns=list(bunch.feature_names))
    df[target_name] = bunch.target
    return df


def _load_diabetes() -> pd.DataFrame:
    return _sklearn_frame(load_diabetes, "target")


def _load_breast_cancer() -> pd.DataFrame:
    return _sklearn_frame(load_breast_cancer, "target")


def _load_wine() -> pd.DataFrame:
    return _sklearn_frame(load_wine, "target")


def _load_iris() -> pd.DataFrame:
    return _sklearn_frame(load_iris, "target")


def _load_california() -> pd.DataFrame:
    # Optional, network/cache-dependent extra; not in the default suite.
    from sklearn.datasets import fetch_california_housing

    bunch = fetch_california_housing()
    full = pd.DataFrame(bunch.data, columns=list(bunch.feature_names))
    full["MedHouseVal"] = bunch.target
    # Subsample deterministically to keep a sweep feasible offline.
    return full.sample(n=2000, random_state=SPLIT_SEED).reset_index(drop=True)


_LOADERS = {
    "delivery_time": _make_delivery_time,
    "diabetes": _load_diabetes,
    "breast_cancer": _load_breast_cancer,
    "wine": _load_wine,
    "iris": _load_iris,
    "california_housing": _load_california,
}


def _numeric_schema(df: pd.DataFrame, target: str) -> dict[str, str]:
    return {c: "numeric" for c in df.columns if c != target}


def _descriptor_for(dataset_id: str) -> DatasetDescriptor:
    """Build the descriptor for a dataset id by inspecting its (cached) frame."""

    df = load_dataset(dataset_id)
    if dataset_id == "delivery_time":
        target = "delivery_time_minutes"
        schema = {c: ("categorical" if c == "traffic_level" else "numeric") for c in df.columns if c != target}
        return DatasetDescriptor(
            dataset_id=dataset_id, task_type=TaskType.regression, feature_schema=schema,
            target=target, primary_metric="rmse", metric_direction=-1,
            split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=list(schema),
        )
    if dataset_id == "diabetes":
        target = "target"
        return DatasetDescriptor(
            dataset_id=dataset_id, task_type=TaskType.regression, feature_schema=_numeric_schema(df, target),
            target=target, primary_metric="rmse", metric_direction=-1,
            split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=[c for c in df.columns if c != target],
        )
    if dataset_id == "california_housing":
        target = "MedHouseVal"
        return DatasetDescriptor(
            dataset_id=dataset_id, task_type=TaskType.regression, feature_schema=_numeric_schema(df, target),
            target=target, primary_metric="rmse", metric_direction=-1,
            split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=[c for c in df.columns if c != target],
        )
    # classification datasets
    target = "target"
    return DatasetDescriptor(
        dataset_id=dataset_id, task_type=TaskType.classification, feature_schema=_numeric_schema(df, target),
        target=target, primary_metric="macro_f1", metric_direction=1,
        split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=[c for c in df.columns if c != target],
    )


# Default suite ids: five fully-offline datasets (FR-016: 5–10).
DEFAULT_SUITE_IDS = ["delivery_time", "diabetes", "breast_cancer", "wine", "iris"]


def load_dataset(dataset_id: str) -> pd.DataFrame:
    """Load a dataset's full frame (deterministic; offline for the default suite)."""

    if dataset_id not in _LOADERS:
        raise KeyError(f"Unknown dataset '{dataset_id}'. Known: {sorted(_LOADERS)}")
    return _LOADERS[dataset_id]()


def get_descriptor(dataset_id: str) -> DatasetDescriptor:
    return _descriptor_for(dataset_id)


def suite(dataset_ids: list[str] | None = None) -> list[DatasetDescriptor]:
    """Return descriptors for the requested ids (or the full default suite)."""

    ids = dataset_ids or DEFAULT_SUITE_IDS
    return [get_descriptor(d) for d in ids]


def frozen_split(
    dataset_id: str, *, n_rows: int | None = None, state_dir: Path | None = None
) -> dict[str, list[int]]:
    """Return frozen train/val/test row-index lists, persisted under ``state/splits/``.

    Computed once from ``SPLIT_SEED`` and cached so every regime/seed/k/m reuses the exact
    same split (FR-017, SC-002). Re-runs read the saved indices rather than recomputing.
    """

    state_dir = Path(state_dir) if state_dir is not None else Path("state")
    splits_dir = state_dir / "splits"
    split_ref = f"{dataset_id}-{BENCHMARK_VERSION}"
    path = splits_dir / f"{split_ref}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        return {k: list(map(int, v)) for k, v in saved.items()}

    if n_rows is None:
        n_rows = len(load_dataset(dataset_id))
    rng = np.random.default_rng(SPLIT_SEED)
    idx = np.arange(n_rows)
    rng.shuffle(idx)
    n_train = int(round(TRAIN_FRAC * n_rows))
    n_val = int(round(VAL_FRAC * n_rows))
    split = {
        "train": idx[:n_train].tolist(),
        "val": idx[n_train : n_train + n_val].tolist(),
        "test": idx[n_train + n_val :].tolist(),
    }
    splits_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split))
    return split
