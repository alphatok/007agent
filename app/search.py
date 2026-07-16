"""Web search tool using DuckDuckGo."""
from duckduckgo_search import DDGS

from agentscope.message import TextBlock
from agentscope.tool import ToolChunk


async def web_search(query: str, max_results: int = 5):  # noqa: ANN201
    """Search the web using DuckDuckGo and return formatted results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        yield ToolChunk(content=[TextBlock(text=f"Search failed: {e}")])
        return

    if not results:
        yield ToolChunk(
            content=[TextBlock(text=f"No results found for: {query}")]
        )
        return

    lines = [f"Search results for: **{query}**\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        href = r.get("href", "")
        body = r.get("body", "")
        if len(body) > 200:
            body = body[:200] + "..."
        lines.append(f"{i}. **{title}**")
        lines.append(f"   {href}")
        lines.append(f"   {body}")
        lines.append("")

    yield ToolChunk(content=[TextBlock(text="\n".join(lines))])