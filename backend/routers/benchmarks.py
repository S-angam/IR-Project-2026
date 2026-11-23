from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from benchmarks.evaluation import evaluate_query, query_catalog
from models.evaluation import QueryEvaluationRequest

router = APIRouter()


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
