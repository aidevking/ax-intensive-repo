import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.schemas.generate import (
    RatingForecastReportRequest,
    RatingRiskReportRequest,
    ReportRequest, ReportResponse, ReportSource,
    ReviewReplyRequest, ReviewReplyResponse,
)
from backend.services.generate_service import FORECAST_SYSTEM_PROMPT
from backend.services.generate_service import GenerateService

logger = logging.getLogger(__name__)
router = APIRouter()

# 서비스 인스턴스 — 프로세스당 1회 생성 (AnalyzeService 재사용)
_service = GenerateService()


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/reply", response_model=ReviewReplyResponse)
async def generate_reply(request: ReviewReplyRequest) -> ReviewReplyResponse:
    """고객 리뷰를 분석해 페인포인트와 신한은행 스타일 답변을 반환한다."""
    if not request.review.strip():
        raise HTTPException(status_code=400, detail="리뷰 텍스트를 입력해주세요.")

    try:
        result = _service.generate_reply(review=request.review)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("generate/reply 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"답변 생성 실패: {e}")

    return ReviewReplyResponse(**result)


@router.post("/report", response_model=ReportResponse)
async def generate_report(request: ReportRequest) -> ReportResponse:
    """분석 결과와 리뷰 RAG 근거를 합쳐 LLM 기반 요약 리포트를 생성한다.

    프롬프트 원칙: 긍정 리뷰는 강점, 부정 리뷰는 약점과 개선 과제의 근거로 사용.
    처리 시간이 로깅되어 30초 이내 기준(성공 기준 ④)을 검증할 수 있다.
    """
    start = time.perf_counter()

    try:
        result = _service.generate_report(
            app_id=request.app_id,
            rag_query=request.rag_query,
            top_k_rag=request.top_k_rag,
            model=request.model,
            platform=request.platform,
            date_from=request.date_from,
            date_to=request.date_to,
        )
    except ValueError as e:
        # OPENAI_API_KEY 미설정 등 설정 오류 → 503
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("generate/report 실패: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"리포트 생성 실패: {e}")

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "generate/report app_id=%s elapsed=%.1fms model=%s",
        request.app_id,
        elapsed_ms,
        result["model_used"],
    )

    # 내부 정렬용 score 필드는 응답 스키마에 노출하지 않는다.
    sources = [
        ReportSource(**{k: v for k, v in s.items() if k != "score"})
        for s in result["sources"]
    ]

    return ReportResponse(
        app_id=request.app_id,
        report=result["report"],
        review_basis=result["review_basis"],
        sources=sources,
        processing_time_ms=round(elapsed_ms, 2),
        model_used=result["model_used"],
    )


@router.post("/report/stream")
async def stream_report(request: ReportRequest) -> StreamingResponse:
    """리뷰 RAG 기반 AI 리포트를 Server-Sent Events 로 스트리밍한다."""

    def event_stream():
        start = time.perf_counter()
        try:
            context = _service.prepare_report_context(
                app_id=request.app_id,
                rag_query=request.rag_query,
                top_k_rag=request.top_k_rag,
                platform=request.platform,
                date_from=request.date_from,
                date_to=request.date_to,
            )
            sources = [
                ReportSource(**{k: v for k, v in s.items() if k != "score"}).model_dump()
                for s in context["sources"]
            ]
            yield _sse("meta", {
                "app_id": request.app_id,
                "review_basis": context["review_basis"],
                "sources": sources,
                "model_used": request.model,
            })

            for delta in _service.stream_llm(context["prompt"], model=request.model):
                yield _sse("delta", {"text": delta})

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "generate/report/stream app_id=%s elapsed=%.1fms model=%s",
                request.app_id,
                elapsed_ms,
                request.model,
            )
            yield _sse("done", {"processing_time_ms": round(elapsed_ms, 2)})
        except ValueError as e:
            yield _sse("error", {"message": str(e)})
        except Exception as e:
            logger.error("generate/report/stream 실패: %s", e, exc_info=True)
            yield _sse("error", {"message": f"리포트 생성 실패: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/rating-forecast/stream")
async def stream_rating_forecast_report(request: RatingForecastReportRequest) -> StreamingResponse:
    """선형회귀 평점 예측 결과를 LLM 해석 리포트로 스트리밍한다."""

    def event_stream():
        start = time.perf_counter()
        try:
            prompt = _service.build_rating_forecast_prompt(
                app_name=request.app_name,
                platform=request.platform,
                forecast=request.forecast,
            )
            yield _sse("meta", {
                "app_key": request.app_key,
                "app_name": request.app_name,
                "platform": request.platform,
                "horizon_months": request.horizon_months,
                "model_used": request.model,
            })

            for delta in _service.stream_llm(
                prompt,
                model=request.model,
                system_prompt=FORECAST_SYSTEM_PROMPT,
            ):
                yield _sse("delta", {"text": delta})

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "generate/rating-forecast/stream app_key=%s elapsed=%.1fms model=%s",
                request.app_key,
                elapsed_ms,
                request.model,
            )
            yield _sse("done", {"processing_time_ms": round(elapsed_ms, 2)})
        except ValueError as e:
            yield _sse("error", {"message": str(e)})
        except Exception as e:
            logger.error("generate/rating-forecast/stream 실패: %s", e, exc_info=True)
            yield _sse("error", {"message": f"평점 예측 리포트 생성 실패: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/rating-risk/stream")
async def stream_rating_risk_report(request: RatingRiskReportRequest) -> StreamingResponse:
    """Stream an LLM report for rating decline risk diagnosis."""

    def event_stream():
        start = time.perf_counter()
        try:
            prompt = _service.build_rating_risk_prompt(
                app_name=request.app_name,
                platform=request.platform,
                risk=request.risk,
            )
            yield _sse("meta", {
                "app_key": request.app_key,
                "app_name": request.app_name,
                "platform": request.platform,
                "horizon_days": request.horizon_days,
                "model_used": request.model,
            })

            for delta in _service.stream_llm(
                prompt,
                model=request.model,
                system_prompt=FORECAST_SYSTEM_PROMPT,
            ):
                yield _sse("delta", {"text": delta})

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "generate/rating-risk/stream app_key=%s elapsed=%.1fms model=%s",
                request.app_key,
                elapsed_ms,
                request.model,
            )
            yield _sse("done", {"processing_time_ms": round(elapsed_ms, 2)})
        except ValueError as e:
            yield _sse("error", {"message": str(e)})
        except Exception as e:
            logger.error("generate/rating-risk/stream 실패: %s", e, exc_info=True)
            yield _sse("error", {"message": f"평점 리스크 리포트 생성 실패: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
