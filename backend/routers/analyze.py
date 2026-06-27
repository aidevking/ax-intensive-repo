from fastapi import APIRouter, HTTPException

from backend.schemas.analyze import (
    DataOperationsResponse,
    EDAResponse,
    PipelineEvidenceResponse,
    SentimentRequest,
    SentimentResponse,
    SentimentResult,
    TopicsResponse,
    Topic,
)
from backend.services.analyze_service import get_analyze_service

router = APIRouter()
analyze_service = get_analyze_service()


@router.post("/sentiment", response_model=SentimentResponse)
async def analyze_sentiment(request: SentimentRequest) -> SentimentResponse:
    """리뷰 배치를 받아 감성 및 불만유형을 분류한다."""
    try:
        reviews_dicts = [r.model_dump() for r in request.reviews]
        raw_results = analyze_service.predict_sentiment(request.app_id, reviews_dicts)
        results = [SentimentResult(**r) for r in raw_results]
        return SentimentResponse(app_id=request.app_id, results=results)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("감성 분석 실패: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="감성 분석 처리 중 오류가 발생했습니다.") from exc


@router.get("/topics", response_model=TopicsResponse)
async def get_topics(app_id: str) -> TopicsResponse:
    """앱별 토픽 분포를 반환한다."""
    try:
        raw_topics = analyze_service.get_topics(app_id)
        topics = [Topic(**t) for t in raw_topics]
        return TopicsResponse(app_id=app_id, topics=topics)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("토픽 모델링 실패: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="토픽 모델링 처리 중 오류가 발생했습니다.") from exc


@router.get("/eda", response_model=EDAResponse)
async def get_eda(app_id: str) -> EDAResponse:
    """별점 추이, 리뷰량 등 EDA 통계를 반환한다."""
    try:
        eda = analyze_service.get_eda(app_id)
        return EDAResponse(**eda)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("EDA 실패: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="EDA 처리 중 오류가 발생했습니다.") from exc


def _get_data_operations_status(app_id: str) -> DataOperationsResponse:
    try:
        evidence = analyze_service.get_data_operations_status(app_id)
        return DataOperationsResponse(**evidence)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Data operations status failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="데이터 운영 현황 처리 중 오류가 발생했습니다.") from exc


@router.get("/data-operations", response_model=DataOperationsResponse)
async def get_data_operations(app_id: str = "com_shinhan_sbanking") -> DataOperationsResponse:
    """리뷰 수집, 전처리, EDA 지표의 운영 현황을 반환한다."""
    return _get_data_operations_status(app_id)


@router.get("/pipeline-evidence", response_model=PipelineEvidenceResponse, include_in_schema=False)
async def get_pipeline_evidence(app_id: str = "com_shinhan_sbanking") -> PipelineEvidenceResponse:
    """Legacy alias for older frontend builds."""
    return _get_data_operations_status(app_id)
