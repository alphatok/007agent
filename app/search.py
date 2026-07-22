"""Web search tool using DuckDuckGo."""
import asyncio

from duckduckgo_search import DDGS

from agentscope.message import TextBlock
from agentscope.tool import ToolChunk
from app.retry import retry_on_failure


def _run_ddgs(query: str, max_results: int) -> list:
    """Execute synchronous DDGS text search."""
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


@retry_on_failure(max_retries=3, backoff=2.0, initial_delay=1.0)
async def _execute_search(query: str, max_results: int = 5) -> list:
    """Execute DDGS search with retry support (retryable core)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_ddgs, query, max_results)


async def web_search(query: str, max_results: int = 5):  # noqa: ANN201
    """Search the web using DuckDuckGo and return formatted results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).
    """
    try:
        results = await _execute_search(query, max_results)
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


@retry_on_failure(max_retries=3, backoff=2.0, initial_delay=1.0)
async def _execute_fetch(url: str) -> str:
    """Fetch a URL and return its text content."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()
            return text[:5000]


async def web_fetch(url: str):  # noqa: ANN201
    """Fetch content from a web page.

    Args:
        url: The URL to fetch content from
    """
    from agentscope.message import ToolResultState

    try:
        content = await _execute_fetch(url)
        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[TextBlock(text=content)],
            metadata={"url": url},
        )
    except Exception as e:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[TextBlock(text=f"Failed to fetch {url}: {e}")],
            metadata={"url": url, "error": str(e)},
        )