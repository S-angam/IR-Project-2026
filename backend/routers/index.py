import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse

from models.index import ConfigResponse, SearchSettings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/index/prepare", status_code=202, tags=["Configuration"])
def prepare_index(request: Request, tasks: BackgroundTasks):
    service = request.app.state.search_service
    try:
        service.begin_preparation()
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error
    tasks.add_task(service.prepare_dense)
    return {"message": "Embedding preparation started. Follow /index/progress."}


@router.get("/config", response_model=ConfigResponse, tags=["Configuration"])
def get_config(request: Request):
    return request.app.state.search_service.info()


@router.get("/index/progress", tags=["Configuration"])
async def index_progress(request: Request):
    """Stream actual progress so the UI does not depend on browser polling timers."""

    async def events():
        while not await request.is_disconnected():
            info = request.app.state.search_service.info()
            payload = {
                "rebuilding": info.rebuilding,
                "progress": info.progress.model_dump(),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/config", response_model=ConfigResponse, tags=["Configuration"])
def update_config(body: SearchSettings, request: Request):
    """Save settings and rebuild only when needed. Existing searches remain available."""
    try:
        return request.app.state.search_service.configure(body)
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error
    except (ValueError, OSError) as error:
        logger.exception("Configuration update failed")
        raise HTTPException(
            500, "Could not prepare the new index. Previous settings remain active."
        ) from error
