from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Method = Literal["bm25", "tfidf", "dense", "hybrid", "hybrid_relaxed"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", json_schema_extra={
        "example": {"query": "A reporter relives the same day in a small town",
                    "methods": ["bm25"], "top_k": 5}
    })
    query: str = Field(min_length=1, max_length=20000)
    methods: list[Method] = Field(default=["bm25"], min_length=1, max_length=5)
    top_k: int = Field(default=5, ge=1, le=50)
    uncertain_clues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(default_factory=list, max_length=5)
    auto_relax: bool = False


class QueryEvaluationRequest(SearchRequest):
    expected_movie_ids: list[Annotated[str, Field(pattern=r"^\d+$")]] = Field(min_length=1, max_length=20)


class SearchResult(BaseModel):
    movie_id: str
    title: str
    year: int | None
    rank: int
    snippet: str
    score: float
    wikipedia_url: str


class MethodResults(BaseModel):
    elapsed_ms: float
    score_type: str
    results: list[SearchResult]
    relaxation: dict | None = None


class SearchResponse(BaseModel):
    query: str
    indexed_movies: int
    index_fingerprint: str
    methods: dict[str, MethodResults]


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_movies: int = Field(default=10000, ge=0, le=250000, description="0 = all usable plots")
    top_k: int = Field(default=5, ge=1, le=50)
    k1: float = Field(default=1.5, gt=0, le=5)
    b: float = Field(default=0.75, ge=0, le=1)
    stemming: bool = True
    remove_stopwords: bool = True
    show_images: bool = True


class IndexProgress(BaseModel):
    phase: Literal["reading", "building", "embedding", "loading", "saving", "ready", "failed"]
    indexed: int = 0
    scanned: int = 0
    target: int | None = None


class ConfigResponse(BaseModel):
    settings: SearchSettings
    indexed_movies: int
    stats: dict[str, int]
    rebuilding: bool
    progress: IndexProgress
    methods: dict[str, dict]
    index_fingerprint: str
