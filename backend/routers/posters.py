import json
import logging
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request as URLRequest
from urllib.request import urlopen

from fastapi import APIRouter, Query, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/posters", tags=["Images"])
def posters(request: Request, movie_ids: str = Query(pattern=r"^\d+(,\d+){0,49}$")):
    """Optional Wikipedia page thumbnails; unavailable images return null."""
    ids = list(dict.fromkeys(movie_ids.split(",")))
    state = request.app.state
    with state.poster_lock:
        return _fetch_posters(state.poster_cache, ids)


def _fetch_posters(cache, ids):
    now = monotonic()
    missing = [
        movie_id
        for movie_id in ids
        if movie_id not in cache or cache[movie_id][0] < now
    ]
    if missing:
        try:
            params = urlencode(
                {
                    "action": "query",
                    "format": "json",
                    "prop": "pageimages",
                    "piprop": "thumbnail",
                    "pageids": "|".join(missing),
                    "pithumbsize": 200,
                    "pilicense": "any",
                    "pilimit": 50,
                }
            )
            url_request = URLRequest(
                "https://en.wikipedia.org/w/api.php?" + params,
                headers={
                    "User-Agent": "IRSangam/0.1 (local movie search; Wikipedia page thumbnails)"
                },
            )
            with urlopen(url_request, timeout=5) as response:
                pages = json.load(response).get("query", {}).get("pages", {})
            if len(cache) > 5000:
                cache.clear()
            for movie_id in missing:
                image = pages.get(movie_id, {}).get("thumbnail", {}).get("source")
                cache[movie_id] = (now + (86400 if image else 300), image)
        except (OSError, ValueError):
            logger.warning(
                "Wikipedia thumbnails unavailable; search results are unaffected"
            )
            for movie_id in missing:
                cache[movie_id] = (now + 60, None)
    return {movie_id: cache.get(movie_id, (0, None))[1] for movie_id in ids}
