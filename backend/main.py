from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from threading import Lock
import uvicorn

from routers.search import router
from search_service import SearchService
from evaluation import EvaluationJob
from experiments import ExperimentJob


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prepare once before accepting requests; searches reuse this instance.
    app.state.search_service = SearchService()
    app.state.evaluation = EvaluationJob(app.state.search_service)
    app.state.experiment = ExperimentJob(app.state.search_service)
    app.state.poster_cache = {}
    app.state.poster_lock = Lock()
    yield


app = FastAPI(title="IRSangam Movie Search", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[
    "http://localhost:5173", "http://127.0.0.1:5173"
], allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])
app.include_router(router)

# Also serve a built React app from the same origin when dist is available.
frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
