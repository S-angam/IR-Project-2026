from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Method = Literal["bm25", "tfidf", "dense", "hybrid", "hybrid_relaxed"]


class DescriptionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(min_length=1, max_length=20000)
    uncertain_clues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=5
    )
    auto_relax: bool = False


class SearchRequest(DescriptionRequest):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "query": "A reporter relives the same day in a small town",
                "methods": ["bm25"],
                "top_k": 5,
            }
        },
    )
    methods: list[Method] = Field(default=["bm25"], min_length=1, max_length=5)
    top_k: int = Field(default=5, ge=1, le=50)


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
