from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.llm import LLMResponse, _estimate_tokens, generate, generate_json


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert _estimate_tokens("hello world") > 0

    def test_empty(self) -> None:
        assert _estimate_tokens("") == 1

    def test_long_text(self) -> None:
        text = "word " * 100
        tokens = _estimate_tokens(text)
        assert 100 < tokens < 200


class TestGenerateJson:
    @pytest.mark.anyio
    async def test_strips_markdown_fences(self) -> None:
        mock_response = LLMResponse(
            text='```json\n{"key": "value"}\n```',
            model="test", provider="test",
            input_tokens=10, output_tokens=10,
            estimated_cost=0.0, latency_ms=100,
        )
        with (
            patch("backend.services.llm.generate", new_callable=AsyncMock, return_value=mock_response),
        ):
            result = await generate_json("test prompt")
        assert result == {"key": "value"}

    @pytest.mark.anyio
    async def test_plain_json(self) -> None:
        mock_response = LLMResponse(
            text='{"status": "compliant"}',
            model="test", provider="test",
            input_tokens=10, output_tokens=10,
            estimated_cost=0.0, latency_ms=100,
        )
        with patch("backend.services.llm.generate", new_callable=AsyncMock, return_value=mock_response):
            result = await generate_json("test")
        assert result["status"] == "compliant"

    @pytest.mark.anyio
    async def test_invalid_json_raises(self) -> None:
        mock_response = LLMResponse(
            text="not json at all",
            model="test", provider="test",
            input_tokens=10, output_tokens=10,
            estimated_cost=0.0, latency_ms=100,
        )
        with patch("backend.services.llm.generate", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(json.JSONDecodeError):
                await generate_json("test")


class TestGenerateFallback:
    @pytest.mark.anyio
    async def test_falls_back_to_ollama(self) -> None:
        ollama_response = LLMResponse(
            text="ollama response",
            model="llama3:8b", provider="ollama",
            input_tokens=10, output_tokens=10,
            estimated_cost=0.0, latency_ms=100,
        )
        with (
            patch("backend.services.llm.settings") as mock_settings,
            patch("backend.services.llm._call_gemini", new_callable=AsyncMock, side_effect=Exception("rate limited")),
            patch("backend.services.llm._call_ollama", new_callable=AsyncMock, return_value=ollama_response),
            patch("backend.services.llm._log_usage", new_callable=AsyncMock),
        ):
            mock_settings.gemini_api_key = "test-key"
            mock_settings.llm_max_retries = 1
            result = await generate("test", prefer="gemini")

        assert result.provider == "ollama"
        assert result.text == "ollama response"

    @pytest.mark.anyio
    async def test_direct_ollama(self) -> None:
        ollama_response = LLMResponse(
            text="direct", model="llama3:8b", provider="ollama",
            input_tokens=5, output_tokens=5, estimated_cost=0.0, latency_ms=50,
        )
        with (
            patch("backend.services.llm._call_ollama", new_callable=AsyncMock, return_value=ollama_response),
            patch("backend.services.llm._log_usage", new_callable=AsyncMock),
        ):
            result = await generate("test", prefer="ollama")
        assert result.provider == "ollama"
