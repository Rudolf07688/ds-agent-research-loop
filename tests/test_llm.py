"""Offline tests for the Gemini/Vertex + minimal-ADK wrapper (US1, T010).

These never make a network call: they assert the bounded-agency posture (Principle III —
the hosted agents carry no tools and cannot transfer) and that schema validation rejects
malformed structured output. The live round-trip is covered by the manual
``entrypoint/smoke_live.py`` script, deliberately excluded from this suite (FR-005).
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from ds_agent_loop import llm
from ds_agent_loop.prompts import NextStepDecision, SeedGeneration, Settings


def _settings() -> Settings:
    return Settings(
        google_cloud_project="test-project",
        google_cloud_location="global",
        gemini_model="gemini-3.5-flash",
    )


def test_hosted_agents_have_no_tools_and_cannot_transfer():
    # Bounded agency: each sanctioned call is a tool-less, non-transferring agent.
    for output_schema, key in (
        (SeedGeneration, "seed_generation"),
        (NextStepDecision, "next_step"),
    ):
        agent = llm._build_agent(
            _settings(),
            name=key,
            instruction="system",
            output_schema=output_schema,
            output_key=key,
        )
        assert agent.tools == []
        assert agent.disallow_transfer_to_parent is True
        assert agent.disallow_transfer_to_peers is True
        assert agent.output_schema is output_schema


def test_configure_vertex_pushes_settings_into_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    import os

    llm._configure_vertex(_settings())
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "TRUE"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "test-project"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "global"


def test_invalid_structured_output_is_rejected(monkeypatch):
    # A malformed agent result must raise LLMError, not return a half-built model.
    class _FakeSession:
        state = {"next_step": {"action": "not_a_valid_action"}}

    class _FakeSessionService:
        async def create_session(self, **_):
            return _FakeSession()

        async def get_session(self, **_):
            return _FakeSession()

    class _FakeRunner:
        def __init__(self, *_, **__):
            self.session_service = _FakeSessionService()

        async def run_async(self, **_):
            if False:
                yield None  # make this an async generator
            return

    monkeypatch.setattr(llm, "InMemoryRunner", _FakeRunner)

    with pytest.raises(llm.LLMError):
        asyncio.run(
            llm.request_next_step(
                _settings(), history_json="[]", allowlist=["LinearRegression"], best_summary="none"
            )
        )


def test_wrapper_surface_is_preserved():
    assert inspect.iscoroutinefunction(llm.generate_seed)
    assert inspect.iscoroutinefunction(llm.request_next_step)
    assert issubclass(llm.LLMError, RuntimeError)
