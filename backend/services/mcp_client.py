from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from backend.services.config import settings

logger = logging.getLogger(__name__)


class MCPError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class MCPClient:
    """Lightweight client for the RegAI MCP server (Streamable HTTP / JSON-RPC 2.0)."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = (base_url or settings.mcp_server_url).rstrip("/")
        self._timeout = timeout
        self._session_id: str | None = None

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/mcp", json=payload, headers=headers)
            resp.raise_for_status()

        session = resp.headers.get("Mcp-Session-Id")
        if session:
            self._session_id = session

        data = resp.json()
        if isinstance(data, list):
            data = data[0]

        if "error" in data:
            e = data["error"]
            raise MCPError(e.get("code", -1), e.get("message", "Unknown error"), e.get("data"))

        return data.get("result")

    async def initialize(self) -> dict[str, Any]:
        result = await self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "regai-backend", "version": "0.1.0"},
        })
        await self._rpc("notifications/initialized")
        return result

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._session_id:
            await self.initialize()

        result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        if not self._session_id:
            await self.initialize()
        result = await self._rpc("tools/list")
        return result.get("tools", [])

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if not self._session_id:
            await self.initialize()
        result = await self._rpc("resources/read", {"uri": uri})
        return result

    async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> dict[str, Any]:
        if not self._session_id:
            await self.initialize()
        result = await self._rpc("prompts/get", {"name": name, "arguments": arguments or {}})
        return result


def extract_text(tool_result: dict[str, Any]) -> str:
    """Extract text content from an MCP tool result."""
    contents = tool_result.get("content", [])
    texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
    return "\n".join(texts)


def extract_json(tool_result: dict[str, Any]) -> Any:
    """Extract and parse JSON from an MCP tool result."""
    import json
    return json.loads(extract_text(tool_result))


_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient()
    return _client
