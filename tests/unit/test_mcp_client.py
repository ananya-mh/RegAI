from __future__ import annotations

import json

from backend.services.mcp_client import MCPError, extract_json, extract_text


class TestExtractText:
    def test_single_text_content(self) -> None:
        result = {"content": [{"type": "text", "text": "hello world"}]}
        assert extract_text(result) == "hello world"

    def test_multiple_text_contents(self) -> None:
        result = {"content": [
            {"type": "text", "text": "line 1"},
            {"type": "text", "text": "line 2"},
        ]}
        assert extract_text(result) == "line 1\nline 2"

    def test_ignores_non_text(self) -> None:
        result = {"content": [
            {"type": "image", "data": "..."},
            {"type": "text", "text": "only text"},
        ]}
        assert extract_text(result) == "only text"

    def test_empty_content(self) -> None:
        assert extract_text({"content": []}) == ""
        assert extract_text({}) == ""


class TestExtractJson:
    def test_parses_json(self) -> None:
        data = {"key": "value", "num": 42}
        result = {"content": [{"type": "text", "text": json.dumps(data)}]}
        assert extract_json(result) == data

    def test_nested_json(self) -> None:
        data = {"requirements": [{"id": "1", "text": "test"}]}
        result = {"content": [{"type": "text", "text": json.dumps(data)}]}
        parsed = extract_json(result)
        assert len(parsed["requirements"]) == 1


class TestMCPError:
    def test_attributes(self) -> None:
        err = MCPError(code=-32600, message="Invalid request", data={"detail": "bad"})
        assert err.code == -32600
        assert str(err) == "Invalid request"
        assert err.data == {"detail": "bad"}

    def test_without_data(self) -> None:
        err = MCPError(code=-1, message="Unknown")
        assert err.data is None
