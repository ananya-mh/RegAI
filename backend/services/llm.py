from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types as genai_types
import httpx

from backend.services.config import settings

logger = logging.getLogger(__name__)

GEMINI_COST_PER_1K_INPUT = 0.0001
GEMINI_COST_PER_1K_OUTPUT = 0.0004

_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: float


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 4 // 3)


async def _call_gemini(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> LLMResponse:
    client = _get_gemini_client()

    config = genai_types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        system_instruction=system_prompt,
    )

    t0 = time.perf_counter()
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=config,
    )
    latency = (time.perf_counter() - t0) * 1000

    text = response.text or ""
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", _estimate_tokens(prompt))
    output_tokens = getattr(usage, "candidates_token_count", _estimate_tokens(text))
    cost = (input_tokens / 1000) * GEMINI_COST_PER_1K_INPUT + (
        output_tokens / 1000
    ) * GEMINI_COST_PER_1K_OUTPUT

    return LLMResponse(
        text=text,
        model=settings.gemini_model,
        provider="google",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        latency_ms=latency,
    )


async def _call_ollama(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> LLMResponse:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        resp.raise_for_status()
    latency = (time.perf_counter() - t0) * 1000

    data = resp.json()
    text = data.get("message", {}).get("content", "")
    input_tokens = data.get("prompt_eval_count", _estimate_tokens(prompt))
    output_tokens = data.get("eval_count", _estimate_tokens(text))

    return LLMResponse(
        text=text,
        model=settings.ollama_model,
        provider="ollama",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=0.0,
        latency_ms=latency,
    )


async def _log_usage(response: LLMResponse, agent_name: str | None = None) -> None:
    try:
        from backend.services.database import async_session
        from backend.models.tables import LLMUsageLog

        async with async_session() as session:
            log = LLMUsageLog(
                model=response.model,
                provider=response.provider,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                estimated_cost=response.estimated_cost,
                agent_name=agent_name,
            )
            session.add(log)
            await session.commit()
    except Exception:
        logger.warning("Failed to log LLM usage", exc_info=True)


async def generate(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    prefer: str = "gemini",
    agent_name: str | None = None,
) -> LLMResponse:
    """Unified LLM call with provider routing and fallback.

    prefer="gemini" tries Gemini first, falls back to Ollama.
    prefer="ollama" goes directly to Ollama.
    """
    response: LLMResponse | None = None

    if prefer == "gemini" and settings.gemini_api_key:
        for attempt in range(1 + settings.llm_max_retries):
            try:
                response = await _call_gemini(prompt, system_prompt, temperature, max_tokens)
                break
            except Exception:
                logger.warning(
                    "Gemini call failed (attempt %d/%d)",
                    attempt + 1,
                    1 + settings.llm_max_retries,
                    exc_info=True,
                )
        if response is None:
            logger.info("Falling back to Ollama after Gemini failure")

    if response is None:
        response = await _call_ollama(prompt, system_prompt, temperature, max_tokens)

    await _log_usage(response, agent_name)
    return response


async def generate_json(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    prefer: str = "gemini",
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Generate and parse a JSON response. Strips markdown fences if present."""
    json_system = (system_prompt or "") + "\nRespond with valid JSON only. No markdown fences."
    response = await generate(
        prompt, json_system.strip(), temperature, max_tokens, prefer, agent_name
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)
