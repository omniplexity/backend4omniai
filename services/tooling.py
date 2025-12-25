import os
import re
import time
import asyncio
from typing import List, Dict

import httpx

WEB_SEARCH_CACHE_TTL = int(os.environ.get("WEB_SEARCH_CACHE_TTL", "600"))
_search_cache: dict[str, tuple[float, List[Dict[str, str]]]] = {}
_search_cache_lock = asyncio.Lock()


def _cache_key(query: str, max_results: int) -> str:
    return f"{max_results}:{query.strip().lower()}"


async def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Lightweight DuckDuckGo lite search scraper. Returns a small set of results
    without needing an API key. Intended as a simple "tool" to enrich model context.
    """
    if WEB_SEARCH_CACHE_TTL > 0:
        cache_key = _cache_key(query, max_results)
        async with _search_cache_lock:
            cached = _search_cache.get(cache_key)
            if cached and cached[0] > time.time():
                return cached[1]
            if cached:
                _search_cache.pop(cache_key, None)

    url = "https://lite.duckduckgo.com/lite/"
    params = {"q": query}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, data=params)
        resp.raise_for_status()

    # DuckDuckGo lite returns anchor tags with class=result-link
    links = re.findall(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        resp.text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    results = []
    for href, title in links:
        clean_title = re.sub(r"<[^>]+>", "", title)
        snippet_match = re.search(
            r'<a[^>]*href="' + re.escape(href) + r'"[^>]*>.*?</a>\s*-\s*(.*?)<',
            resp.text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet = ""
        if snippet_match:
            snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1))

        results.append(
            {
                "title": clean_title.strip()[:200],
                "url": href,
                "snippet": snippet.strip()[:300],
            }
        )
        if len(results) >= max_results:
            break

    if WEB_SEARCH_CACHE_TTL > 0:
        expires_at = time.time() + WEB_SEARCH_CACHE_TTL
        async with _search_cache_lock:
            _search_cache[_cache_key(query, max_results)] = (expires_at, results)

    return results
