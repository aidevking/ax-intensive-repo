from fastapi import APIRouter, HTTPException, Query
from backend.schemas.collect import (
    CollectRequest,
    CollectResponse,
    CollectStatusResponse,
    CollectReviewsResponse,
)
from backend.services import collect_service

router = APIRouter()


@router.post("/reviews", response_model=CollectResponse)
async def collect_reviews(request: CollectRequest) -> CollectResponse:
    """앱스토어 리뷰 수집 작업을 시작하고 job_id를 반환한다."""
    apps = [app.model_dump(mode="json") for app in request.apps]
    job_id = await collect_service.start_collect_job(
        apps=apps,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    return CollectResponse(job_id=job_id, status="queued")


@router.get("/status/{job_id}", response_model=CollectStatusResponse)
async def get_collect_status(job_id: str) -> CollectStatusResponse:
    """수집 작업의 진행 상태, 수집 건수, 완료 여부를 반환한다."""
    job = collect_service.get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job_id={job_id} not found")
    return CollectStatusResponse(
        job_id=job_id,
        status=job["status"],
        count=job["count"],
        completed=job["completed"],
        error=job.get("error"),
    )


@router.get("/reviews/{job_id}", response_model=CollectReviewsResponse)
async def get_collected_reviews(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="한 번에 반환할 최대 건수"),
    offset: int = Query(default=0, ge=0, description="건너뛸 건수 (페이지네이션)"),
) -> CollectReviewsResponse:
    """job_id로 수집된 리뷰 데이터를 페이지네이션해 반환한다."""
    result = collect_service.get_job_reviews(job_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail=f"job_id={job_id} not found")
    return CollectReviewsResponse(**result)
