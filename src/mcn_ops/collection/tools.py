from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolExecutionError(Exception):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_openai_tool(self, strict: bool = False) -> dict[str, Any]:
        function: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
        if strict:
            function["strict"] = True
        return {"type": "function", "function": function}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def has(self, name: str) -> bool:
        return name in self._tools

    def run(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise ToolExecutionError(f"Unknown tool: {name}")
        try:
            return self._tools[name].handler(dict(arguments))
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(str(exc)) from exc

    def definitions(self, strict: bool = False) -> list[dict[str, Any]]:
        return [spec.to_openai_tool(strict=strict) for spec in self._tools.values()]


def parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ToolExecutionError(f"JSON arguments are invalid: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ToolExecutionError("JSON arguments must decode to an object.")
    return parsed
