import logging
import json
import asyncio
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from models import ConfigResponse, QueryEvaluationRequest, SearchRequest, SearchResponse, SearchSettings
from evaluation import evaluate_query, query_catalog
from relaxation import detect_uncertain


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/experiments", tags=["Evaluation"])
def experiment_results(request: Request):
    return request.app.state.experiment.info()


@router.post("/experiments", status_code=202, tags=["Evaluation"])
def start_experiment(request: Request, tasks: BackgroundTasks):
    job = request.app.state.experiment
    try:
        bundle = job.begin()
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error)) from error
    tasks.add_task(job.run, bundle)
    return job.info()


@router.post("/clues/detect", tags=["Search"])
def detect_clues(body: SearchRequest):
    return {"clues": detect_uncertain(body.query)}


@router.post("/search", response_model=SearchResponse, tags=["Search"])
def search(body: SearchRequest, request: Request):
    """Search the shared index. elapsed_ms includes ranking and snippet creation."""
    try:
        return request.app.state.search_service.search(body)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/index/prepare", status_code=202, tags=["Configuration"])
def prepare_index(request: Request, tasks: BackgroundTasks):
    service = request.app.state.search_service
    try:
        service.begin_preparation()
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error
    tasks.add_task(service.prepare_dense)
    return {"message": "Embedding preparation started. Follow /index/progress."}


@router.get("/evaluation", tags=["Evaluation"])
def evaluation_results(request: Request):
    return request.app.state.evaluation.info()


@router.get("/evaluation/queries", tags=["Evaluation"])
def evaluation_queries(request: Request):
    """Show the actual benchmark descriptions, expected IDs and index coverage."""
    return query_catalog(request.app.state.search_service)


@router.post("/evaluation/query", tags=["Evaluation"])
def single_query_evaluation(body: QueryEvaluationRequest, request: Request):
    """Grade one description against expected IDs without changing the saved benchmark."""
    try:
        return evaluate_query(request.app.state.search_service, body)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/evaluation", status_code=202, tags=["Evaluation"])
def start_evaluation(request: Request, tasks: BackgroundTasks):
    job = request.app.state.evaluation
    try:
        bundle = job.begin()
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409, str(error)) from error
    tasks.add_task(job.run, bundle)
    return job.info()


@router.get("/config", response_model=ConfigResponse, tags=["Configuration"])
def get_config(request: Request):
    return request.app.state.search_service.info()


@router.get("/index/progress", tags=["Configuration"])
async def index_progress(request: Request):
    """Stream actual progress so the UI does not depend on browser polling timers."""
    async def events():
        while not await request.is_disconnected():
            info = request.app.state.search_service.info()
            payload = {"rebuilding": info.rebuilding, "progress": info.progress.model_dump()}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.3)
    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@router.put("/config", response_model=ConfigResponse, tags=["Configuration"])
def update_config(body: SearchSettings, request: Request):
    """Save settings and rebuild only when needed. Existing searches remain available."""
    try:
        return request.app.state.search_service.configure(body)
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error
    except (ValueError, OSError) as error:
        logger.exception("Configuration update failed")
        raise HTTPException(500, "Could not prepare the new index. Previous settings remain active.") from error


@router.get("/posters", tags=["Images"])
def posters(request: Request, movie_ids: str = Query(pattern=r"^\d+(,\d+){0,49}$")):
    """Optional Wikipedia page thumbnails; unavailable images return null."""
    ids = list(dict.fromkeys(movie_ids.split(",")))
    state = request.app.state
    with state.poster_lock:
        return _fetch_posters(state.poster_cache, ids)


def _fetch_posters(cache, ids):
    now = monotonic()
    missing = [movie_id for movie_id in ids if movie_id not in cache or cache[movie_id][0] < now]
    if missing:
        try:
            params = urlencode({
                "action": "query", "format": "json", "prop": "pageimages", "piprop": "thumbnail",
                "pageids": "|".join(missing), "pithumbsize": 200, "pilicense": "any", "pilimit": 50,
            })
            url_request = URLRequest("https://en.wikipedia.org/w/api.php?" + params, headers={
                "User-Agent": "IRSangam/0.1 (local movie search; Wikipedia page thumbnails)"
            })
            with urlopen(url_request, timeout=5) as response:
                pages = json.load(response).get("query", {}).get("pages", {})
            if len(cache) > 5000:
                cache.clear()
            for movie_id in missing:
                image = pages.get(movie_id, {}).get("thumbnail", {}).get("source")
                cache[movie_id] = (now + (86400 if image else 300), image)
        except (OSError, ValueError):
            logger.warning("Wikipedia thumbnails unavailable; search results are unaffected")
            for movie_id in missing:
                cache[movie_id] = (now + 60, None)
    return {movie_id: cache.get(movie_id, (0, None))[1] for movie_id in ids}
