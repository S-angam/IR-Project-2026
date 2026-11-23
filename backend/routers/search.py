from fastapi import APIRouter, HTTPException, Request

from models.answers import AnswerResponse
from models.search import DescriptionRequest, SearchRequest, SearchResponse
from retrieval.relaxation import detect_uncertain

router = APIRouter()


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


@router.post("/answer", response_model=AnswerResponse, tags=["Search"])
def answer(body: DescriptionRequest, request: Request):
    """Retrieve plot evidence and ask Gemini for a cited candidate."""
    state = request.app.state
    try:
        return state.answer_generator.generate(state.search_service, body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
