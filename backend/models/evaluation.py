from typing import Annotated

from pydantic import Field

from .search import SearchRequest


class QueryEvaluationRequest(SearchRequest):
    expected_movie_ids: list[Annotated[str, Field(pattern=r"^\d+$")]] = Field(
        min_length=1, max_length=20
    )
