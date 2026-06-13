"""Thin async LLM wrapper.

Exposes one generic helper that performs a JSON-schema-constrained request against an
OpenAI-compatible endpoint and validates the response into a Pydantic model. The two
sanctioned calls (seed generation, next step) build on this helper. The LLM never
returns code the system executes (Constitution Principle III); it only returns JSON that
Python validates and acts on.
"""

from __future__ import annotations

import json
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .prompts import (
    NEXT_STEP_SCHEMA,
    NEXT_STEP_SYSTEM,
    SEED_GENERATION_SCHEMA,
    SEED_GENERATION_SYSTEM,
    SEED_GENERATION_USER,
    NextStepDecision,
    SeedGeneration,
    Settings,
    next_step_user,
)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns malformed/invalid output."""


def build_client(settings: Settings) -> AsyncOpenAI:
    """Construct an async OpenAI-compatible client from centralized settings."""

    if not settings.llm_api_key:
        raise LLMError(
            "Missing LLM API key. Set LLM_API_KEY in your .env (see .env.example)."
        )
    kwargs: dict[str, object] = {"api_key": settings.llm_api_key}
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return AsyncOpenAI(**kwargs)


async def request_structured(
    settings: Settings,
    *,
    system: str,
    user: str,
    schema: dict,
    schema_name: str,
    model_cls: type[T],
    client: AsyncOpenAI | None = None,
) -> T:
    """Make one schema-constrained chat request and validate it into ``model_cls``.

    The provider is asked to return JSON conforming to ``schema``; the raw JSON is then
    re-validated through the Pydantic model so malformed or incomplete output is rejected
    rather than trusted.
    """

    own_client = client is None
    client = client or build_client(settings)
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema,
                    "strict": False,
                },
            },
        )
    except Exception as exc:  # network / API errors
        raise LLMError(f"LLM request failed: {exc}") from exc
    finally:
        if own_client:
            await client.close()

    content = response.choices[0].message.content
    if not content:
        raise LLMError("LLM returned an empty response.")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM returned non-JSON content: {exc}") from exc
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        raise LLMError(f"LLM output failed schema validation: {exc}") from exc


async def generate_seed(settings: Settings) -> SeedGeneration:
    """Seed-generation call: request seed_rows + a reusable data_spec (US1)."""

    return await request_structured(
        settings,
        system=SEED_GENERATION_SYSTEM,
        user=SEED_GENERATION_USER,
        schema=SEED_GENERATION_SCHEMA,
        schema_name="seed_generation",
        model_cls=SeedGeneration,
    )


async def request_next_step(
    settings: Settings,
    *,
    history_json: str,
    allowlist: list[str],
    best_summary: str,
) -> NextStepDecision:
    """Next-step call: reason over history and return a constrained decision (US4)."""

    return await request_structured(
        settings,
        system=NEXT_STEP_SYSTEM,
        user=next_step_user(history_json, allowlist, best_summary),
        schema=NEXT_STEP_SCHEMA,
        schema_name="next_step",
        model_cls=NextStepDecision,
    )
