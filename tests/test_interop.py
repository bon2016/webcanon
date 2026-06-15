"""Framework-neutral interop helpers (document shape + tool schema).

These prove the affinity claims in docs/ai-framework-affinity.md: the core
exposes shapes that map onto LangChain/LlamaIndex documents and OpenAI/Anthropic
tool definitions without any framework dependency.
"""

import httpx

from webcanon import (
    RETRIEVE_TOOL,
    WebCanon,
    as_anthropic_tool,
    as_openai_tool,
)
from webcanon.config import FetchConfig, RetrievalConfig


def _client():
    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if req.url.path == "/llms.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><title>Doc</title><body><h1>H</h1><p>Body</p></body></html>",
        )

    transport = httpx.MockTransport(routes)
    http = httpx.Client(transport=transport, follow_redirects=False)
    return WebCanon(RetrievalConfig(fetch=FetchConfig(block_private_addresses=False)),
                    client=http)


def test_to_document_has_neutral_keys():
    result = _client().retrieve_url("https://example.com/page")
    doc = result.to_document()
    # Same content under all three common keys.
    assert doc["content"] == doc["page_content"] == doc["text"]
    assert "# H" in doc["content"]
    md = doc["metadata"]
    assert md["source"] == "https://example.com/page"
    assert md["source_hash"].startswith("sha256:")
    assert md["robots_verdict"] == "allowed_implicit"
    assert "quality_score" in md


def test_to_markdown_with_citation_appends_source():
    result = _client().retrieve_url("https://example.com/page")
    text = result.to_markdown_with_citation()
    assert "Source:" in text
    assert "https://example.com/page" in text


def test_openai_tool_shape():
    tool = as_openai_tool()
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "webcanon_retrieve"
    assert "url" in tool["function"]["parameters"]["properties"]
    assert tool["function"]["parameters"]["required"] == ["url"]
    # Returned copy, not shared module-level schema dicts.
    assert tool["function"]["parameters"] is not RETRIEVE_TOOL["input_schema"]

def test_anthropic_tool_shape():
    tool = as_anthropic_tool()
    assert tool["name"] == "webcanon_retrieve"
    assert tool["input_schema"]["properties"]["ai_reasoning"]["type"] == "boolean"
    # Returned copy, not the shared module-level dicts.
    assert tool is not RETRIEVE_TOOL
    assert tool["input_schema"] is not RETRIEVE_TOOL["input_schema"]
