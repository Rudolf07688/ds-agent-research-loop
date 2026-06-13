"""LLM Autonomous Data Scientist — library package.

Public API for consumers (e.g. ``entrypoint/``): the toy single-run loop (``run_loop``), the
memory-regime ablation cell runner (``run_cell``) and factorial sweep (``run_sweep``), and the
central settings object. The single-purpose submodules (``prompts``, ``llm``, ``data_gen``,
``train``, ``history``, ``memory``, ``compaction``, ``benchmark``, ``store``, ``experiment``,
``analysis``, ``main``) remain importable directly.
"""

from __future__ import annotations

from .experiment import run_sweep
from .main import run_cell, run_loop
from .prompts import Settings

__all__ = ["run_loop", "run_cell", "run_sweep", "Settings"]
