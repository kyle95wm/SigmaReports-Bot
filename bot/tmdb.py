import json
import urllib.request
from typing import List


def _tmdb_get(url: str, bearer_token: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def fetch_tmdb_titles(bearer_token: str, limit_each: int = 30) -> List[str]:
    """
    Returns a list of titles from TMDB (trending TV + trending movies).
    Uses v3 endpoints with Bearer auth.
    """
    titles: list[str] = []

    tv = _tmdb_get("https://api.themoviedb.org/3/trending/tv/day", bearer_token)
    mv = _tmdb_get("https://api.themoviedb.org/3/trending/movie/day", bearer_token)

    for item in (tv.get("results") or [])[:limit_each]:
        name = item.get("name")
        if name:
            titles.append(str(name))

    for item in (mv.get("results") or [])[:limit_each]:
        name = item.get("title")
        if name:
            titles.append(str(name))

    # de-dupe while preserving order
    seen = set()
    out = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
