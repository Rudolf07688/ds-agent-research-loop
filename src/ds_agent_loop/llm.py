"""Thin LLM wrapper: Google Gemini on Vertex AI, hosted by a minimal ADK agent.

Each of the two sanctioned calls (seed generation, next step) is hosted by its own
minimal ADK ``LlmAgent`` configured with a Pydantic ``output_schema`` and **no tools**.
Setting ``output_schema`` makes the agent emit structured JSON validated against the
schema and disables tool/transfer use — which is exactly the bounded-agency posture the
constitution requires (Principles II & III): the LLM only returns JSON that Python
validates and acts on, never code the system executes.

Authentication is Application Default Credentials (ADC); the Vertex project/location and
the Gemini model come from the centralized ``Settings``. The module's public surface
(``generate_seed`` / ``request_next_step`` / ``LLMError``) is unchanged so the rest of the
library is agnostic to the backend.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from .prompts import (
    NEXT_STEP_SYSTEM,
    SEED_GENERATION_SYSTEM,
    SEED_GENERATION_USER,
    NextStepDecision,
    SeedGeneration,
    Settings,
    next_step_user,
)

T = TypeVar("T", bound=BaseModel)

APP_NAME = "ds-agent-loop"
USER_ID = "loop"


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns malformed/invalid output."""


def _configure_vertex(settings: Settings) -> None:
    """Point the ADK/``google.genai`` backend at Vertex AI from centralized settings.

    ADK builds its ``google.genai`` client from these environment variables; Settings is
    the single source of truth (Principle VIII) and is pushed into the environment here.
    Credentials themselves are ADC — discovered from the environment, never stored here.
    """

    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE" if settings.use_vertexai else "FALSE"
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location


def _build_agent(
    settings: Settings,
    *,
    name: str,
    instruction: str,
    output_schema: type[BaseModel],
    output_key: str,
) -> LlmAgent:
    """Construct a minimal, tool-less ADK agent for one sanctioned structured call."""

    return LlmAgent(
        name=name,
        model=settings.gemini_model,
        instruction=instruction,
        output_schema=output_schema,
        output_key=output_key,
        tools=[],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


async def _run_structured(
    settings: Settings,
    *,
    name: str,
    instruction: str,
    user: str,
    output_schema: type[T],
    output_key: str,
) -> T:
    """Run one minimal ADK agent and validate its structured output into ``output_schema``.

    The agent is asked to return JSON conforming to ``output_schema``; the result stored in
    session state is re-validated through the Pydantic model so malformed or incomplete
    output is rejected rather than trusted.
    """

    _configure_vertex(settings)
    agent = _build_agent(
        settings,
        name=name,
        instruction=instruction,
        output_schema=output_schema,
        output_key=output_key,
    )
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    message = types.Content(role="user", parts=[types.Part.from_text(text=user)])
    try:
        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID
        )
        async for _event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            pass
        session = await runner.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session.id
        )
    except Exception as exc:  # auth / network / API errors -> fail fast (FR-009)
        raise LLMError(f"Gemini/Vertex request failed: {exc}") from exc

    raw = None if session is None else session.state.get(output_key)
    if raw is None:
        raise LLMError("Agent returned no structured output.")
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Agent returned non-JSON content: {exc}") from exc
    try:
        return output_schema.model_validate(raw)
    except ValidationError as exc:
        raise LLMError(f"LLM output failed schema validation: {exc}") from exc


async def generate_seed(settings: Settings) -> SeedGeneration:
    """Seed-generation call: request seed_rows + a reusable data_spec (US1)."""

    return await _run_structured(
        settings,
        name="seed_generation",
        instruction=SEED_GENERATION_SYSTEM,
        user=SEED_GENERATION_USER,
        output_schema=SeedGeneration,
        output_key="seed_generation",
    )


async def request_next_step(
    settings: Settings,
    *,
    history_json: str,
    allowlist: list[str],
    best_summary: str,
) -> NextStepDecision:
    """Next-step call: reason over history and return a constrained decision (US4)."""

    return await _run_structured(
        settings,
        name="next_step",
        instruction=NEXT_STEP_SYSTEM,
        user=next_step_user(history_json, allowlist, best_summary),
        output_schema=NextStepDecision,
        output_key="next_step",
    )
