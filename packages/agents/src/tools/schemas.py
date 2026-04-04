"""OpenAI-compatible tool definitions for agent runtime."""

from __future__ import annotations

from typing import Any


def build_agent_tool_definitions(
    *,
    include_navigation: bool,
    include_memory_recall: bool,
) -> list[dict[str, Any]]:
    """Return ``tools`` payload for :meth:`LLMClient.completion`."""
    tools: list[dict[str, Any]] = []
    if include_navigation:
        glob_items = {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Optional path globs relative to project root (e.g. 'src/**/*.py'). "
                "If omitted, searches up to 400 Python files under the project."
            ),
        }
        tools.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "nav_find_symbol",
                        "description": (
                            "Locate a top-level class or function name across the codebase."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"},
                                "file_globs": glob_items,
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "nav_where_used",
                        "description": (
                            "Find lines referencing a symbol (excludes definitions). "
                            "Useful before refactors."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"},
                                "file_globs": glob_items,
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "nav_module_map",
                        "description": (
                            "Summarize import dependencies per file from parsed chunks."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_globs": glob_items,
                            },
                            "required": [],
                        },
                    },
                },
            ]
        )
    if include_memory_recall:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "memory_recall",
                    "description": (
                        "Retrieve durable and working memory context for the current agent. "
                        "Pass a short natural-language query."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        )
    return tools
