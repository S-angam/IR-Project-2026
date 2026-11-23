import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

import uvicorn
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from benchmarks.evaluation import EvaluationJob
from benchmarks.experiments import ExperimentJob
from routers.benchmarks import router as benchmark_router
from routers.index import router as index_router
from routers.posters import router as poster_router
from routers.search import router as search_router
from services.answers import AnswerGenerator
from services.search import SearchService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prepare once before accepting requests; searches reuse this instance.
    app.state.search_service = SearchService()
    key = os.environ.get("GOOGLE_API_KEY") or dotenv_values(
        Path(__file__).with_name(".env")
    ).get("GOOGLE_API_KEY")
    app.state.answer_generator = AnswerGenerator(
        app.state.search_service.document.get("answer", {}), key
    )
    app.state.evaluation = EvaluationJob(app.state.search_service)
    app.state.experiment = ExperimentJob(app.state.search_service)
    app.state.poster_cache = {}
    app.state.poster_lock = Lock()
    yield


app = FastAPI(title="IRSangam Movie Search", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
app.include_router(search_router)
app.include_router(index_router)
app.include_router(benchmark_router)
app.include_router(poster_router)

# Also serve a built React app from the same origin when dist is available.
frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
