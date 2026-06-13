"""Alembic migration environment for the ablation Postgres schema (Principle IV).

The connection URL is derived from the centralized ``Settings`` (DATABASE_URL), normalized
to the psycopg driver — so the same migrations apply locally and in the container with no
per-environment edits. ``target_metadata`` is the single source of truth defined in
``store.py``, which keeps ``alembic revision --autogenerate`` honest for future changes.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from ds_agent_loop.prompts import Settings
from ds_agent_loop.store import metadata, normalize_url

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

target_metadata = metadata


def _url() -> str:
    # A URL set on the config (e.g. passed programmatically) wins; otherwise use Settings.
    return config.get_main_option("sqlalchemy.url") or normalize_url(Settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
