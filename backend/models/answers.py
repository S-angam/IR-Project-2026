from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .search import Method


class AnswerSource(BaseModel):
    movie_id: str
    title: str
    year: int | None
    wikipedia_url: str
    excerpt: str


class AnswerResponse(BaseModel):
    query: str
    method: Method
    model: str
    status: Literal["answered", "insufficient_evidence", "unavailable"]
    explanation: str
    movie_id: str | None = None
    evidence_quote: str | None = None
    sources: list[AnswerSource]


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    movie_id: str | None
    explanation: str = Field(min_length=1, max_length=900)
    evidence_quote: str | None
