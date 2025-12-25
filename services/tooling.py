import re
from typing import List, Dict

import httpx


async def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Lightweight DuckDuckGo lite search scraper. Returns a small set of results
    without needing an API key. Intended as a simple "tool" to enrich model context.
    """
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

    return results
