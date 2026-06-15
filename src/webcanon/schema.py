"""Provider-neutral tool schema for WebCanon retrieval.

A single JSON-Schema description of the ``retrieve`` tool that adapters reuse
to register WebCanon with function-calling LLMs (OpenAI / Anthropic), MCP
servers, and agent frameworks. Keeping it here (zero extra dependencies) means
every adapter agrees on the same argument contract.

Example (Anthropic / OpenAI tool definition)::

    from webcanon.schema import RETRIEVE_TOOL, as_openai_tool
    tools = [as_openai_tool()]            # OpenAI chat.completions "tools"
    # or use RETRIEVE_TOOL directly for Anthropic's `tools` parameter.
"""

from __future__ import annotations

from typing import Any

RETRIEVE_TOOL_NAME = "webcanon_retrieve"

RETRIEVE_TOOL_DESCRIPTION = (
    "Retrieve a web page as clean Markdown after evaluating robots.txt, "
    "resolving llms.txt alternatives, and recording provenance. Returns "
    "policy-checked, citation-ready content for grounding."
)

RETRIEVE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The absolute http(s) URL to retrieve.",
        },
        "ai_reasoning": {
            "type": "boolean",
            "description": (
                "If true, consult llms.txt and prefer LLM-friendly Markdown "
                "alternatives (still subject to robots.txt)."
            ),
            "default": False,
        },
    },
    "required": ["url"],
    "additionalProperties": False,
}

# Anthropic-style tool definition (name / description / input_schema).
RETRIEVE_TOOL: dict[str, Any] = {
    "name": RETRIEVE_TOOL_NAME,
    "description": RETRIEVE_TOOL_DESCRIPTION,
    "input_schema": RETRIEVE_INPUT_SCHEMA,
}


def as_openai_tool() -> dict[str, Any]:
    """Return the tool in OpenAI ``tools=[...]`` (function) shape."""

    import copy

    return {
        "type": "function",
        "function": {
            "name": RETRIEVE_TOOL_NAME,
            "description": RETRIEVE_TOOL_DESCRIPTION,
            "parameters": copy.deepcopy(RETRIEVE_INPUT_SCHEMA),
        },
    }


def as_anthropic_tool() -> dict[str, Any]:
    """Return the tool in Anthropic ``tools=[...]`` shape."""

    import copy

    return copy.deepcopy(RETRIEVE_TOOL)
