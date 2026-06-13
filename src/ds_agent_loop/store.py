"""Durable persistence for the memory-compaction ablation (Principles IV, IX, X).

A single Postgres instance is the durable home of cells, experiment records, the exact
memory views shown, compaction artifacts (+ lineage), and structured logs. Tables are
defined once with SQLAlchemy Core; all writes are idempotent ``INSERT ... ON CONFLICT DO
UPDATE`` on the natural key so a re-run or resume neither duplicates nor corrupts state
(FR-014, SC-007). Everything exports to human-readable JSON/CSV (FR-014a).

Two store implementations share one duck-typed interface:

* ``Store``   — SQLAlchemy/psycopg against Postgres (production + the integration test).
* ``FakeStore`` — pure in-memory Python with the same idempotent semantics, so the unit
  suite stays hermetic and zero-network (research Decision 2).

A schema deviation from ``contracts/db-schema.md`` worth noting: ``memory_views`` is keyed
by ``(cell_id, iteration)`` (its idempotent upsert key) with ``content_hash`` as a column,
rather than ``content_hash`` as a global primary key. Identical rendered memory can recur
across cells (e.g. an empty early history under ``recent_only`` for two seeds), which would
collide a global content-hash PK; ``(cell_id, iteration)`` is the correct natural key and
``ExperimentRecord.memory_view_ref`` still carries the content-addressable hash value.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from .prompts import ExperimentCell, ExperimentRecord, MemoryView

# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------


def normalize_url(database_url: str) -> str:
    """Force the psycopg (v3) driver. Accepts a bare ``postgresql://`` URL (as supplied
    by ``docker-compose.yml``) and rewrites it to ``postgresql+psycopg://``."""

    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def make_engine(database_url: str) -> Engine:
    """Build a SQLAlchemy engine for the given URL (psycopg driver)."""

    return create_engine(normalize_url(database_url), future=True)


def upgrade_to_head(database_url: str | None = None) -> None:
    """Apply Alembic migrations up to ``head`` (Principle IV).

    The schema is owned by the migrations under ``alembic/`` — this is the sanctioned way
    to create/evolve it (no operational ``create_all``). Called at app/container startup so a
    fresh database reaches the current schema deterministically. ``alembic.ini`` and the
    ``alembic/`` directory are resolved relative to the repository root.
    """

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", normalize_url(database_url))
    command.upgrade(cfg, "head")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema (SQLAlchemy Core) — contracts/db-schema.md
# ---------------------------------------------------------------------------

metadata = MetaData()

cells = Table(
    "cells",
    metadata,
    Column("cell_id", String, primary_key=True),
    Column("dataset_id", String, nullable=False),
    Column("regime", String, nullable=False),
    Column("seed", Integer, nullable=False),
    Column("k", Integer, nullable=False),
    Column("m", Integer, nullable=False),
    Column("budget", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("error", String),
    Column("last_iteration", Integer),
    Column("repro", JSONB),
    Column("created_ts", String),
    Column("updated_ts", String),
)

experiment_records = Table(
    "experiment_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cell_id", String, nullable=False),
    Column("iteration", Integer, nullable=False),
    Column("dataset_id", String),
    Column("regime", String),
    Column("seed", Integer),
    Column("k", Integer),
    Column("m", Integer),
    Column("dataset_size", Integer),
    Column("model_name", String),
    Column("hyperparameters", JSONB),
    Column("proposal", JSONB),
    Column("executed_config", JSONB),
    Column("metrics", JSONB),
    Column("val_metrics", JSONB),
    Column("test_metrics", JSONB),
    Column("improved", Boolean),
    Column("rejected", Boolean),
    Column("memory_view_ref", String),
    Column("runtime_s", Float),
    Column("rationale", String),
    Column("timestamp", String),
    UniqueConstraint("cell_id", "iteration", name="uq_record_cell_iter"),
)

memory_views = Table(
    "memory_views",
    metadata,
    Column("cell_id", String, nullable=False),
    Column("iteration", Integer, nullable=False),
    Column("regime", String, nullable=False),
    Column("included_record_ids", JSONB),
    Column("included_artifact_id", String),
    Column("rendered_text", String),
    Column("content_hash", String),
    Column("prompt_token_count", Integer),
    UniqueConstraint("cell_id", "iteration", name="uq_view_cell_iter"),
)

compaction_artifacts = Table(
    "compaction_artifacts",
    metadata,
    Column("artifact_id", String, primary_key=True),
    Column("cell_id", String, nullable=False),
    Column("trigger_iteration", Integer, nullable=False),
    Column("artifact", JSONB),
    Column("source_record_ids", JSONB),
    Column("created_ts", String),
    UniqueConstraint("cell_id", "trigger_iteration", name="uq_artifact_cell_trigger"),
)

run_logs = Table(
    "run_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cell_id", String),
    Column("iteration", Integer),
    Column("level", String),
    Column("event", String),
    Column("payload", JSONB),
    Column("ts", String),
)


# ---------------------------------------------------------------------------
# Store (Postgres, SQLAlchemy Core)
# ---------------------------------------------------------------------------


class Store:
    """Postgres-backed store. Idempotent upserts keyed on natural keys."""

    def __init__(self, engine: Engine, *, create: bool = False) -> None:
        # The schema is owned by Alembic migrations (Principle IV); the operational path does
        # NOT create tables. ``create=True`` builds them directly and is permitted ONLY for
        # ephemeral/test schemas (it is not used by the app or sweep).
        self.engine = engine
        if create:
            metadata.create_all(engine)

    # --- cells ----------------------------------------------------------------
    def upsert_cell(self, cell: ExperimentCell) -> None:
        row = {
            "cell_id": cell.cell_id,
            "dataset_id": cell.dataset_id,
            "regime": cell.regime.value,
            "seed": cell.seed,
            "k": cell.k,
            "m": cell.m,
            "budget": cell.budget,
            "status": cell.status.value,
            "error": cell.error,
            "last_iteration": cell.last_iteration,
            "repro": cell.repro,
            "created_ts": cell.created_ts or _now(),
            "updated_ts": _now(),
        }
        stmt = pg_insert(cells).values(**row).on_conflict_do_update(
            index_elements=["cell_id"],
            set_={
                "status": row["status"],
                "error": row["error"],
                "last_iteration": row["last_iteration"],
                "repro": row["repro"],
                "updated_ts": row["updated_ts"],
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_cell(self, cell_id: str) -> ExperimentCell | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(cells).where(cells.c.cell_id == cell_id)
            ).mappings().first()
        return _row_to_cell(row) if row else None

    def all_cells(self) -> list[ExperimentCell]:
        with self.engine.begin() as conn:
            rows = conn.execute(select(cells).order_by(cells.c.cell_id)).mappings().all()
        return [_row_to_cell(r) for r in rows]

    # --- experiment records ---------------------------------------------------
    def append_record(self, record: ExperimentRecord) -> None:
        row = _record_to_row(record)
        stmt = pg_insert(experiment_records).values(**row).on_conflict_do_update(
            index_elements=["cell_id", "iteration"],
            set_={k: row[k] for k in row if k not in ("cell_id", "iteration")},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_records(self, cell_id: str) -> list[ExperimentRecord]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(experiment_records)
                .where(experiment_records.c.cell_id == cell_id)
                .order_by(experiment_records.c.iteration)
            ).mappings().all()
        return [_row_to_record(r) for r in rows]

    # --- memory views ---------------------------------------------------------
    def save_view(self, view: MemoryView) -> None:
        row = {
            "cell_id": view.cell_id,
            "iteration": view.iteration,
            "regime": view.regime.value,
            "included_record_ids": view.included_record_ids,
            "included_artifact_id": view.included_artifact_id,
            "rendered_text": view.rendered_text,
            "content_hash": view.content_hash,
            "prompt_token_count": view.prompt_token_count,
        }
        stmt = pg_insert(memory_views).values(**row).on_conflict_do_update(
            index_elements=["cell_id", "iteration"],
            set_={k: row[k] for k in row if k not in ("cell_id", "iteration")},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_views(self, cell_id: str) -> list[MemoryView]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(memory_views)
                .where(memory_views.c.cell_id == cell_id)
                .order_by(memory_views.c.iteration)
            ).mappings().all()
        return [_row_to_view(r) for r in rows]

    # --- compaction artifacts -------------------------------------------------
    def save_artifact(
        self,
        *,
        cell_id: str,
        trigger_iteration: int,
        artifact: dict[str, Any],
        source_record_ids: list[int],
    ) -> str:
        artifact_id = f"{cell_id}@{trigger_iteration}"
        row = {
            "artifact_id": artifact_id,
            "cell_id": cell_id,
            "trigger_iteration": trigger_iteration,
            "artifact": artifact,
            "source_record_ids": source_record_ids,
            "created_ts": _now(),
        }
        stmt = pg_insert(compaction_artifacts).values(**row).on_conflict_do_update(
            index_elements=["cell_id", "trigger_iteration"],
            set_={
                "artifact": row["artifact"],
                "source_record_ids": row["source_record_ids"],
                "created_ts": row["created_ts"],
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        return artifact_id

    def get_artifacts(self, cell_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(compaction_artifacts)
                .where(compaction_artifacts.c.cell_id == cell_id)
                .order_by(compaction_artifacts.c.trigger_iteration)
            ).mappings().all()
        return [dict(r) for r in rows]

    def latest_artifact(self, cell_id: str) -> dict[str, Any] | None:
        arts = self.get_artifacts(cell_id)
        return arts[-1] if arts else None

    # --- structured logs ------------------------------------------------------
    def log(
        self,
        *,
        cell_id: str | None,
        iteration: int | None,
        level: str,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                run_logs.insert().values(
                    cell_id=cell_id,
                    iteration=iteration,
                    level=level,
                    event=event,
                    payload=payload,
                    ts=_now(),
                )
            )

    def get_logs(self, cell_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(run_logs)
                .where(run_logs.c.cell_id == cell_id)
                .order_by(run_logs.c.id)
            ).mappings().all()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# FakeStore (in-memory, hermetic) — same interface, same idempotent semantics
# ---------------------------------------------------------------------------


class FakeStore:
    """In-memory store mirroring ``Store``'s idempotent natural-key semantics."""

    def __init__(self) -> None:
        self._cells: dict[str, ExperimentCell] = {}
        self._records: dict[tuple[str, int], ExperimentRecord] = {}
        self._views: dict[tuple[str, int], MemoryView] = {}
        self._artifacts: dict[tuple[str, int], dict[str, Any]] = {}
        self._logs: list[dict[str, Any]] = []
        self._next_id = 1

    def upsert_cell(self, cell: ExperimentCell) -> None:
        existing = self._cells.get(cell.cell_id)
        created = existing.created_ts if existing else (cell.created_ts or _now())
        stored = cell.model_copy(update={"created_ts": created, "updated_ts": _now()})
        self._cells[cell.cell_id] = stored

    def get_cell(self, cell_id: str) -> ExperimentCell | None:
        c = self._cells.get(cell_id)
        return c.model_copy(deep=True) if c else None

    def all_cells(self) -> list[ExperimentCell]:
        return [c.model_copy(deep=True) for c in sorted(self._cells.values(), key=lambda x: x.cell_id)]

    def append_record(self, record: ExperimentRecord) -> None:
        key = (record.cell_id or "", record.iteration)
        self._records[key] = record.model_copy(deep=True)

    def get_records(self, cell_id: str) -> list[ExperimentRecord]:
        items = [r for (c, _), r in self._records.items() if c == cell_id]
        return [r.model_copy(deep=True) for r in sorted(items, key=lambda r: r.iteration)]

    def save_view(self, view: MemoryView) -> None:
        self._views[(view.cell_id, view.iteration)] = view.model_copy(deep=True)

    def get_views(self, cell_id: str) -> list[MemoryView]:
        items = [v for (c, _), v in self._views.items() if c == cell_id]
        return [v.model_copy(deep=True) for v in sorted(items, key=lambda v: v.iteration)]

    def save_artifact(
        self,
        *,
        cell_id: str,
        trigger_iteration: int,
        artifact: dict[str, Any],
        source_record_ids: list[int],
    ) -> str:
        artifact_id = f"{cell_id}@{trigger_iteration}"
        self._artifacts[(cell_id, trigger_iteration)] = {
            "artifact_id": artifact_id,
            "cell_id": cell_id,
            "trigger_iteration": trigger_iteration,
            "artifact": artifact,
            "source_record_ids": list(source_record_ids),
            "created_ts": _now(),
        }
        return artifact_id

    def get_artifacts(self, cell_id: str) -> list[dict[str, Any]]:
        items = [a for (c, _), a in self._artifacts.items() if c == cell_id]
        return [dict(a) for a in sorted(items, key=lambda a: a["trigger_iteration"])]

    def latest_artifact(self, cell_id: str) -> dict[str, Any] | None:
        arts = self.get_artifacts(cell_id)
        return arts[-1] if arts else None

    def log(
        self,
        *,
        cell_id: str | None,
        iteration: int | None,
        level: str,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        self._logs.append(
            {
                "id": self._next_id,
                "cell_id": cell_id,
                "iteration": iteration,
                "level": level,
                "event": event,
                "payload": dict(payload),
                "ts": _now(),
            }
        )
        self._next_id += 1

    def get_logs(self, cell_id: str) -> list[dict[str, Any]]:
        return [dict(line) for line in self._logs if line["cell_id"] == cell_id]


# ---------------------------------------------------------------------------
# Row <-> model conversion
# ---------------------------------------------------------------------------


def _row_to_cell(row: Any) -> ExperimentCell:
    return ExperimentCell.model_validate(
        {
            "cell_id": row["cell_id"],
            "dataset_id": row["dataset_id"],
            "regime": row["regime"],
            "seed": row["seed"],
            "k": row["k"],
            "m": row["m"],
            "budget": row["budget"],
            "status": row["status"],
            "error": row["error"],
            "last_iteration": row["last_iteration"],
            "repro": row["repro"] or {},
            "created_ts": row["created_ts"],
            "updated_ts": row["updated_ts"],
        }
    )


_RECORD_COLS = (
    "cell_id",
    "iteration",
    "dataset_id",
    "regime",
    "seed",
    "k",
    "m",
    "dataset_size",
    "model_name",
    "hyperparameters",
    "proposal",
    "executed_config",
    "metrics",
    "val_metrics",
    "test_metrics",
    "improved",
    "rejected",
    "memory_view_ref",
    "runtime_s",
    "rationale",
    "timestamp",
)


def _record_to_row(record: ExperimentRecord) -> dict[str, Any]:
    proposal = record.proposal.model_dump() if record.proposal is not None else None
    return {
        "cell_id": record.cell_id,
        "iteration": record.iteration,
        "dataset_id": record.dataset_id,
        "regime": record.regime.value if record.regime else None,
        "seed": record.seed,
        "k": record.k,
        "m": record.m,
        "dataset_size": record.dataset_size,
        "model_name": record.model_name,
        "hyperparameters": record.hyperparameters,
        "proposal": proposal,
        "executed_config": record.executed_config,
        "metrics": record.metrics,
        "val_metrics": record.val_metrics,
        "test_metrics": record.test_metrics,
        "improved": record.improved,
        "rejected": record.rejected,
        "memory_view_ref": record.memory_view_ref,
        "runtime_s": record.runtime_s,
        "rationale": record.rationale,
        "timestamp": record.timestamp,
    }


def _row_to_record(row: Any) -> ExperimentRecord:
    return ExperimentRecord.model_validate(
        {
            "iteration": row["iteration"],
            "dataset_size": row["dataset_size"] or 0,
            "model_name": row["model_name"] or "",
            "hyperparameters": row["hyperparameters"] or {},
            "metrics": row["metrics"] or {},
            "rationale": row["rationale"] or "",
            "timestamp": row["timestamp"] or "",
            "cell_id": row["cell_id"],
            "dataset_id": row["dataset_id"],
            "regime": row["regime"],
            "seed": row["seed"],
            "k": row["k"],
            "m": row["m"],
            "proposal": row["proposal"],
            "executed_config": row["executed_config"] or {},
            "val_metrics": row["val_metrics"] or {},
            "test_metrics": row["test_metrics"] or {},
            "improved": bool(row["improved"]),
            "rejected": bool(row["rejected"]),
            "memory_view_ref": row["memory_view_ref"],
            "runtime_s": row["runtime_s"],
        }
    )


def _row_to_view(row: Any) -> MemoryView:
    return MemoryView.model_validate(
        {
            "cell_id": row["cell_id"],
            "iteration": row["iteration"],
            "regime": row["regime"],
            "included_record_ids": row["included_record_ids"] or [],
            "included_artifact_id": row["included_artifact_id"],
            "rendered_text": row["rendered_text"] or "",
            "content_hash": row["content_hash"] or "",
            "prompt_token_count": row["prompt_token_count"] or 0,
        }
    )


# ---------------------------------------------------------------------------
# Structured logging sink (Principle X, research Decision 3)
# ---------------------------------------------------------------------------

_stdout_logger = logging.getLogger("ds_agent_loop.run")
if not _stdout_logger.handlers:
    _handler = logging.StreamHandler(stream=sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _stdout_logger.addHandler(_handler)
    _stdout_logger.setLevel(logging.INFO)


class CellLogger:
    """Binds a cell context and emits each event as a JSON line to stdout AND to the
    ``run_logs`` table, so a run is diagnosable live and queryable after the fact."""

    def __init__(self, store: Any, cell_id: str) -> None:
        self._store = store
        self._cell_id = cell_id

    def log(self, level: str, event: str, iteration: int | None = None, **payload: Any) -> None:
        line = {
            "cell_id": self._cell_id,
            "iteration": iteration,
            "level": level,
            "event": event,
            **payload,
        }
        _stdout_logger.info(json.dumps(line, default=str))
        self._store.log(
            cell_id=self._cell_id,
            iteration=iteration,
            level=level,
            event=event,
            payload=payload,
        )

    def info(self, event: str, iteration: int | None = None, **payload: Any) -> None:
        self.log("INFO", event, iteration, **payload)

    def warning(self, event: str, iteration: int | None = None, **payload: Any) -> None:
        self.log("WARNING", event, iteration, **payload)

    def error(self, event: str, iteration: int | None = None, **payload: Any) -> None:
        self.log("ERROR", event, iteration, **payload)


def get_logger(store: Any, cell_id: str) -> CellLogger:
    """Return a ``CellLogger`` bound to ``cell_id`` (research Decision 3)."""

    return CellLogger(store, cell_id)


# ---------------------------------------------------------------------------
# Export to human-readable JSON/CSV (FR-014a, Principle IV) — supports T034/US4
# ---------------------------------------------------------------------------


def export(store: Any, out_dir: str | Path, *, outcomes: dict[str, Any] | None = None) -> Path:
    """Export every cell's records/views/artifacts/logs to JSON/CSV under ``out_dir``.

    Layout (contracts/db-schema.md §Export):
      <out_dir>/<cell_id>/records.json | memory_views.json | artifacts.json | logs.csv
      <out_dir>/cells.csv      (index of all cells + status)
      <out_dir>/outcomes.json  (analysis summaries, when provided)
    """

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_cells = store.all_cells()

    # cells.csv index
    with (out / "cells.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["cell_id", "dataset_id", "regime", "seed", "k", "m", "budget", "status", "last_iteration", "error"]
        )
        for c in all_cells:
            writer.writerow(
                [c.cell_id, c.dataset_id, c.regime.value, c.seed, c.k, c.m, c.budget,
                 c.status.value, c.last_iteration, c.error or ""]
            )

    for c in all_cells:
        cell_dir = out / _safe_dir(c.cell_id)
        cell_dir.mkdir(parents=True, exist_ok=True)
        records = store.get_records(c.cell_id)
        (cell_dir / "records.json").write_text(
            json.dumps([r.model_dump(mode="json") for r in records], indent=2)
        )
        views = store.get_views(c.cell_id)
        (cell_dir / "memory_views.json").write_text(
            json.dumps([v.model_dump(mode="json") for v in views], indent=2)
        )
        (cell_dir / "artifacts.json").write_text(
            json.dumps(store.get_artifacts(c.cell_id), indent=2, default=str)
        )
        logs = store.get_logs(c.cell_id)
        with (cell_dir / "logs.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "iteration", "level", "event", "payload", "ts"])
            for line in logs:
                writer.writerow(
                    [line.get("id"), line.get("iteration"), line.get("level"),
                     line.get("event"), json.dumps(line.get("payload"), default=str), line.get("ts")]
                )

    if outcomes is not None:
        (out / "outcomes.json").write_text(json.dumps(outcomes, indent=2, default=str))
    return out


def _safe_dir(cell_id: str) -> str:
    """Make a filesystem-safe directory name from a cell id."""

    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in cell_id)


# ---------------------------------------------------------------------------
# CLI: `python -m ds_agent_loop.store export --out outputs/export` (FR-014a)
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    from .prompts import Settings

    parser = argparse.ArgumentParser(description="Postgres store utilities for the ablation.")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="export all cells to human-readable JSON/CSV")
    exp.add_argument("--out", default="outputs/export")
    args = parser.parse_args()

    settings = Settings()
    store = Store(make_engine(settings.database_url), create=False)
    out = export(store, args.out)
    print(f"Exported {len(store.all_cells())} cells to {out}")


if __name__ == "__main__":
    main()
