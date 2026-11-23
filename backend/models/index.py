from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_movies: int = Field(
        default=10000, ge=0, le=250000, description="0 = all usable plots"
    )
    top_k: int = Field(default=5, ge=1, le=50)
    k1: float = Field(default=1.5, gt=0, le=5)
    b: float = Field(default=0.75, ge=0, le=1)
    stemming: bool = True
    remove_stopwords: bool = True
    show_images: bool = True


class IndexProgress(BaseModel):
    phase: Literal[
        "reading", "building", "embedding", "loading", "saving", "ready", "failed"
    ]
    indexed: int = 0
    scanned: int = 0
    target: int | None = None


class DenseIndexInfo(BaseModel):
    engine: Literal["ChromaDB"] = "ChromaDB"
    collection: str
    stored_vectors: int
    missing_vectors: int


class ConfigResponse(BaseModel):
    settings: SearchSettings
    indexed_movies: int
    stats: dict[str, int]
    rebuilding: bool
    progress: IndexProgress
    methods: dict[str, dict]
    dense_index: DenseIndexInfo
    index_fingerprint: str
