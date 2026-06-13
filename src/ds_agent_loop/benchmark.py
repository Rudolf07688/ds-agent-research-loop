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

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.datasets import (
    load_breast_cancer,
    load_diabetes,
    load_iris,
    load_wine,
)
from sklearn.model_selection import train_test_split

from .prompts import TaskType
from .train import CLASSIFIER_ALLOWLIST, MODEL_ALLOWLIST, allowlist_for

BENCHMARK_VERSION = "v1"

# Fixed split seed — fixed across the whole suite so splits are reproducible and
# independent of the cell seed (Principle V, SC-002).
SPLIT_SEED = 20260613
TRAIN_FRAC = 0.6
VAL_FRAC = 0.2  # remainder (0.2) is test

# The frozen action space available to the agent on every benchmark member. The dataset/split
# is fixed, so ``expand_dataset`` is intentionally NOT offered (Principle XIII / FR-016): the
# only manipulated variable is the memory regime, never the data.
DEFAULT_ACTION_SPACE = ["keep_model", "tune_hyperparameters", "switch_model", "stop"]

# Default per-member budget (N iterations) and patience (k rounds w/o improvement) — mirror the
# Settings defaults so a materialized member is self-describing without reading the environment.
DEFAULT_BUDGET = 30
DEFAULT_PATIENCE = 3


class BenchmarkDriftError(RuntimeError):
    """A recomputed content hash / fingerprint diverged from the persisted one under an
    existing benchmark version — fixed-factor drift without a version bump (FR-014/019)."""


class SplitError(ValueError):
    """A frozen split is degenerate: an empty partition, or a classification split that drops
    a class from any partition (edge cases — flagged at materialization, not run time)."""


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

    # --- feature 004: persisted fixed factors (data-model.md §DatasetDescriptor) -----------
    provenance: str = "curated_real"  # "anchored_synthetic" | "curated_real"
    budget: int = DEFAULT_BUDGET  # N iterations
    patience: int | None = DEFAULT_PATIENCE  # k rounds w/o improvement (null = run to budget)
    action_space: list[str] = Field(default_factory=lambda: list(DEFAULT_ACTION_SPACE))
    # Persisted explicitly (derived from ``allowlist_for(task_type)``) so allowlist drift is
    # detectable independent of the code that produced it.
    model_allowlist: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_fixed_factors(self) -> "DatasetDescriptor":
        """Reject metric/task-type or allowlist/task-type mismatches at declaration (edge case).

        classification ⇒ classification metric (direction +1) and allowlist ⊆ classifiers;
        regression ⇒ regression metric (direction -1) and allowlist ⊆ regressors. An empty
        ``model_allowlist`` is auto-populated from the task-appropriate allowlist so descriptors
        built outside ``_descriptor_for`` stay valid.
        """

        if self.provenance not in ("anchored_synthetic", "curated_real"):
            raise ValueError(f"Unknown provenance '{self.provenance}'.")

        if self.task_type is TaskType.classification:
            allowed_models, metric, direction = set(CLASSIFIER_ALLOWLIST), "macro_f1", 1
        else:
            allowed_models, metric, direction = set(MODEL_ALLOWLIST), "rmse", -1

        if self.primary_metric != metric:
            raise ValueError(
                f"{self.task_type.value} member must use metric '{metric}', got '{self.primary_metric}'."
            )
        if self.metric_direction != direction:
            raise ValueError(
                f"{self.task_type.value} metric '{metric}' direction must be {direction}, got {self.metric_direction}."
            )

        if not self.model_allowlist:
            object.__setattr__(self, "model_allowlist", sorted(allowlist_for(self.task_type)))
        extra = set(self.model_allowlist) - allowed_models
        if extra:
            raise ValueError(
                f"{self.task_type.value} allowlist contains non-{self.task_type.value} models: {sorted(extra)}."
            )
        return self


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
    # delivery_time is the locally-generated anchored-synthetic task; every other default-suite
    # member is a curated-real sklearn dataset (data-model.md §DatasetDescriptor.provenance).
    provenance = "anchored_synthetic" if dataset_id == "delivery_time" else "curated_real"
    if dataset_id == "delivery_time":
        target = "delivery_time_minutes"
        schema = {c: ("categorical" if c == "traffic_level" else "numeric") for c in df.columns if c != target}
        return DatasetDescriptor(
            dataset_id=dataset_id, task_type=TaskType.regression, feature_schema=schema,
            target=target, primary_metric="rmse", metric_direction=-1,
            split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=list(schema),
            provenance=provenance,
        )
    if dataset_id == "diabetes":
        target = "target"
        return DatasetDescriptor(
            dataset_id=dataset_id, task_type=TaskType.regression, feature_schema=_numeric_schema(df, target),
            target=target, primary_metric="rmse", metric_direction=-1,
            split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=[c for c in df.columns if c != target],
            provenance=provenance,
        )
    if dataset_id == "california_housing":
        target = "MedHouseVal"
        return DatasetDescriptor(
            dataset_id=dataset_id, task_type=TaskType.regression, feature_schema=_numeric_schema(df, target),
            target=target, primary_metric="rmse", metric_direction=-1,
            split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=[c for c in df.columns if c != target],
            provenance=provenance,
        )
    # classification datasets
    target = "target"
    return DatasetDescriptor(
        dataset_id=dataset_id, task_type=TaskType.classification, feature_schema=_numeric_schema(df, target),
        target=target, primary_metric="macro_f1", metric_direction=1,
        split_ref=f"{dataset_id}-{BENCHMARK_VERSION}", feature_names=[c for c in df.columns if c != target],
        provenance=provenance,
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


class FrozenSplit(BaseModel):
    """A fixed assignment of row indices to partitions, content-hashed (data-model.md §FrozenSplit).

    Subscriptable (``split["train"]``) so it is a drop-in for the legacy ``dict`` split passed to
    ``train.score_on_split`` and ``main.run_cell``.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    benchmark_version: str = BENCHMARK_VERSION
    train: list[int]
    val: list[int]
    test: list[int]
    content_hash: str
    stratified: bool = False

    def __getitem__(self, key: str) -> list[int]:
        if key not in ("train", "val", "test"):
            raise KeyError(key)
        return getattr(self, key)


def content_hash(dataset_id: str, version: str, split: dict[str, list[int]]) -> str:
    """sha256 over canonical ``(dataset_id, version, {train,val,test sorted})`` — stable across
    processes (SC-003), so a reload can assert byte-identical reuse."""

    payload = {
        "dataset_id": dataset_id,
        "benchmark_version": version,
        "train": sorted(int(i) for i in split["train"]),
        "val": sorted(int(i) for i in split["val"]),
        "test": sorted(int(i) for i in split["test"]),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def member_fingerprint(descriptor: "DatasetDescriptor", split: FrozenSplit) -> str:
    """sha256 over a member's fixed factors (task type, metric+direction, action space,
    allowlist, budget, patience, split policy). A change to any factor changes the fingerprint;
    materialization under an existing version asserts equality (FR-014, SC-005)."""

    payload = {
        "dataset_id": descriptor.dataset_id,
        "benchmark_version": descriptor.benchmark_version,
        "task_type": descriptor.task_type.value,
        "provenance": descriptor.provenance,
        "primary_metric": descriptor.primary_metric,
        "metric_direction": descriptor.metric_direction,
        "budget": descriptor.budget,
        "patience": descriptor.patience,
        "action_space": sorted(descriptor.action_space),
        "model_allowlist": sorted(descriptor.model_allowlist),
        "split_content_hash": split.content_hash,
        "stratified": split.stratified,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_partition_invariants(train: list[int], val: list[int], test: list[int], n_rows: int) -> None:
    """No empty partition; pairwise disjoint; union covers exactly ``range(n_rows)`` (no leakage)."""

    if not train or not val or not test:
        raise SplitError("a frozen split partition is empty (degenerate split).")
    union = sorted(train + val + test)
    if union != list(range(n_rows)):
        raise SplitError("frozen split partitions overlap or do not cover all rows (test leakage).")


def _stratified_indices(y: np.ndarray, n_rows: int) -> tuple[list[int], list[int], list[int]]:
    """Two-stage stratified split (train vs temp, then val vs test) under ``SPLIT_SEED``.

    Every class must survive in every partition, else the member is flagged (``SplitError``)
    at materialization rather than at run time (research.md Decision 2)."""

    idx = np.arange(n_rows)
    test_size = 1.0 - TRAIN_FRAC
    train_idx, temp_idx = train_test_split(
        idx, test_size=test_size, random_state=SPLIT_SEED, stratify=y, shuffle=True
    )
    # Split the held-out remainder evenly into val/test (VAL_FRAC == test fraction == 0.2).
    val_idx, test_idx = train_test_split(
        temp_idx, test_size=0.5, random_state=SPLIT_SEED, stratify=y[temp_idx], shuffle=True
    )
    classes = set(np.unique(y).tolist())
    for name, part in (("train", train_idx), ("val", val_idx), ("test", test_idx)):
        if set(np.unique(y[part]).tolist()) != classes:
            raise SplitError(f"stratified split dropped a class from the '{name}' partition.")
    return sorted(int(i) for i in train_idx), sorted(int(i) for i in val_idx), sorted(int(i) for i in test_idx)


def frozen_split(
    dataset_id: str, *, n_rows: int | None = None, state_dir: Path | None = None
) -> FrozenSplit:
    """Return a frozen, content-hashed train/val/test split, mirrored under ``state/splits/``.

    Classification members are stratified so every class appears in every partition (research.md
    Decision 2); regression keeps the fixed-seed shuffle. Computed once from ``SPLIT_SEED`` and
    cached so every regime/seed/k/m reuses the exact same split (FR-017, SC-002). A cached split
    is re-hashed on read and fails loudly if it has drifted.
    """

    state_dir = Path(state_dir) if state_dir is not None else Path("state")
    splits_dir = state_dir / "splits"
    split_ref = f"{dataset_id}-{BENCHMARK_VERSION}"
    path = splits_dir / f"{split_ref}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if "content_hash" in saved:  # full FrozenSplit mirror
            fs = FrozenSplit.model_validate(saved)
            recomputed = content_hash(fs.dataset_id, fs.benchmark_version, {"train": fs.train, "val": fs.val, "test": fs.test})
            if recomputed != fs.content_hash:
                raise BenchmarkDriftError(f"cached split for {split_ref} failed its content-hash check.")
            return fs
        # legacy index-only mirror (feature 003) — ignore and recompute the modern split.

    descriptor = get_descriptor(dataset_id)
    df = load_dataset(dataset_id)
    if n_rows is None:
        n_rows = len(df)

    if descriptor.task_type is TaskType.classification:
        y = df[descriptor.target].to_numpy()
        train, val, test = _stratified_indices(y, n_rows)
        stratified = True
    else:
        rng = np.random.default_rng(SPLIT_SEED)
        idx = np.arange(n_rows)
        rng.shuffle(idx)
        n_train = int(round(TRAIN_FRAC * n_rows))
        n_val = int(round(VAL_FRAC * n_rows))
        train = idx[:n_train].tolist()
        val = idx[n_train : n_train + n_val].tolist()
        test = idx[n_train + n_val :].tolist()
        stratified = False

    _assert_partition_invariants(train, val, test, n_rows)
    ch = content_hash(dataset_id, BENCHMARK_VERSION, {"train": train, "val": val, "test": test})
    fs = FrozenSplit(
        dataset_id=dataset_id, benchmark_version=BENCHMARK_VERSION,
        train=train, val=val, test=test, content_hash=ch, stratified=stratified,
    )
    splits_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(fs.model_dump_json())
    return fs


# ---------------------------------------------------------------------------
# Materialization, versioning, load + export (feature 004) — benchmark-api.md
# ---------------------------------------------------------------------------


def _member_row(descriptor: "DatasetDescriptor", split: FrozenSplit, fingerprint: str) -> dict[str, Any]:
    return {
        "dataset_id": descriptor.dataset_id,
        "benchmark_version": descriptor.benchmark_version,
        "task_type": descriptor.task_type.value,
        "provenance": descriptor.provenance,
        "target": descriptor.target,
        "primary_metric": descriptor.primary_metric,
        "metric_direction": descriptor.metric_direction,
        "budget": descriptor.budget,
        "patience": descriptor.patience,
        "feature_schema": descriptor.feature_schema,
        "feature_names": list(descriptor.feature_names),
        "action_space": list(descriptor.action_space),
        "model_allowlist": list(descriptor.model_allowlist),
        "fingerprint": fingerprint,
    }


def _split_row(split: FrozenSplit, n_rows: int) -> dict[str, Any]:
    return {
        "dataset_id": split.dataset_id,
        "benchmark_version": split.benchmark_version,
        "train_idx": list(split.train),
        "val_idx": list(split.val),
        "test_idx": list(split.test),
        "content_hash": split.content_hash,
        "stratified": split.stratified,
        "n_rows": n_rows,
    }


def _descriptor_from_member_row(row: dict[str, Any]) -> "DatasetDescriptor":
    return DatasetDescriptor(
        dataset_id=row["dataset_id"],
        task_type=TaskType(row["task_type"]),
        feature_schema=dict(row["feature_schema"] or {}),
        target=row["target"],
        primary_metric=row["primary_metric"],
        metric_direction=row["metric_direction"],
        split_ref=f"{row['dataset_id']}-{row['benchmark_version']}",
        benchmark_version=row["benchmark_version"],
        feature_names=list(row["feature_names"] or []),
        provenance=row["provenance"],
        budget=row["budget"],
        patience=row["patience"],
        action_space=list(row["action_space"] or []),
        model_allowlist=list(row["model_allowlist"] or []),
    )


def _split_from_row(row: dict[str, Any]) -> FrozenSplit:
    return FrozenSplit(
        dataset_id=row["dataset_id"],
        benchmark_version=row["benchmark_version"],
        train=list(row["train_idx"]),
        val=list(row["val_idx"]),
        test=list(row["test_idx"]),
        content_hash=row["content_hash"],
        stratified=row["stratified"],
    )


def _resolve_for_version(
    dataset_id: str, version: str
) -> tuple["DatasetDescriptor", FrozenSplit, str]:
    """Build the descriptor, frozen split (content-hashed under ``version``) and member
    fingerprint for ``dataset_id`` — the single source of truth shared by ``materialize_suite``
    and ``check_version_drift`` so both compute identical, version-consistent values."""

    descriptor = get_descriptor(dataset_id).model_copy(
        update={"benchmark_version": version, "split_ref": f"{dataset_id}-{version}"}
    )
    split = frozen_split(dataset_id).model_copy(update={"benchmark_version": version})
    ch = content_hash(dataset_id, version, {"train": split.train, "val": split.val, "test": split.test})
    split = split.model_copy(update={"content_hash": ch})
    return descriptor, split, member_fingerprint(descriptor, split)


def check_version_drift(store: Any, descriptor: "DatasetDescriptor", *, version: str = BENCHMARK_VERSION) -> None:
    """Reject a fixed-factor change made without a version bump (FR-014, SC-005, US3).

    Recomputes the member fingerprint (incl. the version-consistent split content hash) and
    compares it to the persisted one under ``version``. A mismatch raises ``BenchmarkDriftError``;
    a brand-new version (no persisted row) is allowed and coexists with the old.
    """

    existing = store.get_benchmark_member(descriptor.dataset_id, version)
    if existing is None:
        return
    _, _, recomputed = _resolve_for_version(descriptor.dataset_id, version)
    if recomputed != existing["fingerprint"]:
        raise BenchmarkDriftError(
            f"Member '{descriptor.dataset_id}' changed a fixed factor under existing version "
            f"'{version}' without a version bump (fingerprint mismatch). Bump BENCHMARK_VERSION."
        )


def materialize_suite(
    store: Any, dataset_ids: list[str] | None = None, *, version: str = BENCHMARK_VERSION
) -> list["DatasetDescriptor"]:
    """Materialize each member into ``benchmark_members`` / ``benchmark_splits`` (benchmark-api.md).

    For each member: build the descriptor, compute its frozen split + content hash + fingerprint,
    and upsert keyed by ``(dataset_id, version)``. Idempotent — a pre-existing row whose hash or
    fingerprint differs raises ``BenchmarkDriftError`` (FR-019, FR-014); a match is a no-op.
    Returns the materialized descriptors.
    """

    ids = dataset_ids or DEFAULT_SUITE_IDS
    materialized: list[DatasetDescriptor] = []
    for dataset_id in ids:
        descriptor, split, fingerprint = _resolve_for_version(dataset_id, version)
        df = load_dataset(dataset_id)

        existing_split = store.get_benchmark_split(dataset_id, version)
        if existing_split is not None and existing_split["content_hash"] != split.content_hash:
            raise BenchmarkDriftError(
                f"Re-materializing '{dataset_id}' under '{version}' produced a different split "
                f"content hash than persisted — data drift (FR-019)."
            )
        check_version_drift(store, descriptor, version=version)

        store.upsert_benchmark_member(_member_row(descriptor, split, fingerprint))
        store.upsert_benchmark_split(_split_row(split, len(df)))
        materialized.append(descriptor)
    return materialized


def load_member(
    store: Any, dataset_id: str, *, version: str = BENCHMARK_VERSION
) -> tuple["DatasetDescriptor", FrozenSplit, pd.DataFrame]:
    """Load a materialized member by id (benchmark-api.md).

    Reads the persisted descriptor + split, regenerates the rows via the deterministic loader,
    and asserts the recomputed content hash matches the persisted one (byte-identical reuse,
    SC-001/003). The split assignment is read, never re-drawn (no test-row leakage). Raises
    ``BenchmarkDriftError`` on a hash mismatch.
    """

    member_row = store.get_benchmark_member(dataset_id, version)
    split_row = store.get_benchmark_split(dataset_id, version)
    if member_row is None or split_row is None:
        raise KeyError(f"Member '{dataset_id}' is not materialized under version '{version}'.")

    descriptor = _descriptor_from_member_row(member_row)
    split = _split_from_row(split_row)
    df = load_dataset(dataset_id)
    recomputed = content_hash(dataset_id, version, {"train": split.train, "val": split.val, "test": split.test})
    if recomputed != split.content_hash:
        raise BenchmarkDriftError(
            f"Loaded split for '{dataset_id}@{version}' failed its content-hash check "
            f"(persisted={split.content_hash}, recomputed={recomputed})."
        )
    if len(df) != split_row["n_rows"]:
        raise BenchmarkDriftError(
            f"Regenerated rows for '{dataset_id}@{version}' ({len(df)}) differ from persisted "
            f"n_rows ({split_row['n_rows']}) — synthetic data drift."
        )
    return descriptor, split, df


def export_member(
    store: Any, dataset_id: str, out_dir: str | Path, *, version: str = BENCHMARK_VERSION
) -> Path:
    """Export a member to ``<out_dir>/<version>/<dataset_id>/`` as descriptor.json + rows.csv +
    split.json, then reload and re-assert the content hash (FR-018, SC-006).

    The round-trip guarantees DB-free, byte-identical reuse: the written CSV reloads to the same
    rows and the same content hash as the persisted member.
    """

    descriptor, split, df = load_member(store, dataset_id, version=version)
    dest = Path(out_dir) / version / dataset_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "descriptor.json").write_text(descriptor.model_dump_json(indent=2))
    (dest / "split.json").write_text(split.model_dump_json(indent=2))
    df.to_csv(dest / "rows.csv", index=False)

    # Re-assert the round-trip: reload the CSV and recompute the hash from the persisted split.
    reloaded = pd.read_csv(dest / "rows.csv")
    if len(reloaded) != len(df):
        raise BenchmarkDriftError(f"Exported rows for '{dataset_id}' did not round-trip (row count).")
    recomputed = content_hash(dataset_id, version, {"train": split.train, "val": split.val, "test": split.test})
    if recomputed != split.content_hash:
        raise BenchmarkDriftError(f"Exported split for '{dataset_id}' failed its content-hash re-check.")
    return dest


# ---------------------------------------------------------------------------
# CLI: `python -m ds_agent_loop.benchmark {materialize,export}` (quickstart §2/§5)
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    from . import store as store_mod
    from .prompts import Settings

    parser = argparse.ArgumentParser(description="Materialize / export the versioned benchmark suite.")
    sub = parser.add_subparsers(dest="command", required=True)

    mat = sub.add_parser("materialize", help="materialize the suite into Postgres (idempotent)")
    mat.add_argument("--datasets", default=None, help="comma-separated ids (default: full suite)")
    mat.add_argument("--version", default=BENCHMARK_VERSION)

    exp = sub.add_parser("export", help="export a materialized member to JSON/CSV")
    exp.add_argument("dataset_id")
    exp.add_argument("out_dir")
    exp.add_argument("--version", default=BENCHMARK_VERSION)

    args = parser.parse_args()
    settings = Settings()
    store_mod.upgrade_to_head(settings.database_url)  # schema owned by Alembic (Principle IV)
    store = store_mod.Store(store_mod.make_engine(settings.database_url))

    if args.command == "materialize":
        ids = [s.strip() for s in args.datasets.split(",")] if args.datasets else None
        members = materialize_suite(store, ids, version=args.version)
        print(f"Materialized {len(members)} members under {args.version}: {[m.dataset_id for m in members]}")
    elif args.command == "export":
        dest = export_member(store, args.dataset_id, args.out_dir, version=args.version)
        print(f"Exported {args.dataset_id}@{args.version} to {dest}")


if __name__ == "__main__":
    main()
