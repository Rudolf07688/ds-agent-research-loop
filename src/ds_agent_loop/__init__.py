"""LLM Autonomous Data Scientist (Toy) Loop — library package.

Public API for consumers (e.g. ``entrypoint/``): the loop entrypoint and the central
settings object. The single-purpose submodules (``prompts``, ``llm``, ``data_gen``,
``train``, ``history``, ``main``) remain importable directly.
"""

from __future__ import annotations

from .main import run_loop
from .prompts import Settings

__all__ = ["run_loop", "Settings"]
