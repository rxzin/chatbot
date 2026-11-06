"""Web search behind a small interface, so the provider can be swapped."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from core.logging import logger

_EXA_URL = "https://api.exa.ai/search"
_TIMEOUT_SECONDS = 20.0
# Excerpt length per page. Keeps what the model reads small; pages are untrusted text.
_HIGHLIGHT_CHARS = 1200


class SearchUnavailableError(Exception):
    """The provider couldn't be reached, refused the request, or is out of credits."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None


def is_web_url(url: str) -> bool:
    """Only http and https links are kept; anything else is dropped."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class SearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        """Return up to num_results results. Raise SearchUnavailableError on failure."""

    async def close(self) -> None:
        """Release connections."""


class ExaSearchProvider(SearchProvider):
    name = "exa"

    def __init__(self, api_key: str):
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
        )

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        body = {
            "query": query,
            "type": "auto",
            "numResults": num_results,
            "contents": {"highlights": {"maxCharacters": _HIGHLIGHT_CHARS}},
        }
        try:
            response = await self._client.post(_EXA_URL, json=body)
        except httpx.HTTPError as exc:
            raise SearchUnavailableError("Exa request failed") from exc
        if response.status_code != 200:
            # 401 bad key, 402 out of credits, 429 rate limited, 5xx outage.
            logger.warning("Exa search returned HTTP %s", response.status_code)
            raise SearchUnavailableError(f"Exa returned HTTP {response.status_code}")

        data = response.json()
        cost = (data.get("costDollars") or {}).get("total")
        if cost is not None:
            logger.info("Exa search cost $%s", cost)

        results = []
        for item in data.get("results") or []:
            url = str(item.get("url") or "")
            if not is_web_url(url):
                continue
            highlights = item.get("highlights") or []
            snippet = " … ".join(h.strip() for h in highlights if h) or (item.get("text") or "")
            results.append(
                SearchResult(
                    title=str(item.get("title") or url)[:300],
                    url=url,
                    snippet=snippet[: _HIGHLIGHT_CHARS * 2],
                    published_date=item.get("publishedDate"),
                )
            )
        return results

    async def close(self) -> None:
        await self._client.aclose()


def build_search_provider(provider: str, exa_api_key: str) -> Optional[SearchProvider]:
    """None turns web search off: the tool isn't offered to the model."""
    if provider == "exa" and exa_api_key:
        return ExaSearchProvider(exa_api_key)
    if provider == "exa":
        logger.warning("SEARCH_PROVIDER is exa but EXA_API_KEY is empty; web search is off")
    return None
