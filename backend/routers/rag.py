"""
RAG 라우터 — 근거 문서 인덱싱 및 검색 엔드포인트.

역할 경계:
  - POST /rag/index  : 공개 자료 문서를 청크 분할·임베딩·인덱싱한다.
  - POST /rag/search : 질의와 관련된 근거 문서를 검색하여 반환한다.
  - GET  /rag/info   : 인덱스 현황을 조회한다.

이 라우터는 LLM 호출이나 답변 생성을 하지 않는다.
검색 결과를 generate 모듈에 전달하는 것이 전부다.
"""

from fastapi import APIRouter, HTTPException

from backend.schemas.rag import (
    CollectionInfoResponse,
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from backend.services.rag_service import RagService

router = APIRouter()

# 전역 싱글턴 — 임베딩 모델을 프로세스당 1회만 로드한다
rag_service = RagService()


@router.post("/index", response_model=IndexResponse)
async def index_documents(request: IndexRequest) -> IndexResponse:
    """
    공개 자료 문서 목록을 청크 분할·임베딩·인덱싱한다.

    - 문서가 0건이면 400 반환.
    - 동일 source 는 기존 청크를 삭제 후 재인덱싱(중복 방지).
    - 답변 문장을 생성하지 않는다.
    """
    if not request.documents:
        raise HTTPException(status_code=400, detail="문서 목록이 비어있습니다.")

    docs = [doc.model_dump() for doc in request.documents]
    result = rag_service.index_documents(
        documents=docs,
        collection_name=request.collection_name,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail="인덱싱 실패: 유효한 문서가 없습니다.")

    return IndexResponse(
        status=result["status"],
        indexed_count=result["indexed_count"],
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest) -> SearchResponse:
    """
    질의와 관련된 공개 자료 근거 문서를 검색하여 반환한다.

    - 컬렉션이 비어있거나 존재하지 않으면 404 반환.
    - 결과에는 항상 출처 메타데이터(app_name, source, date)가 포함된다.
    - 답변 문장을 생성하지 않는다.
    """
    info = rag_service.get_collection_info(request.collection_name)
    if not info["exists"] or info["count"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"컬렉션 '{request.collection_name}'이 비어있거나 존재하지 않습니다. 먼저 /rag/index 를 호출하세요.",
        )

    raw_results = rag_service.search(
        query=request.query,
        top_k=request.top_k,
        app_name=request.app_name,
        collection_name=request.collection_name,
    )

    results = [SearchResult(**r) for r in raw_results]

    return SearchResponse(query=request.query, results=results)


@router.get("/info", response_model=CollectionInfoResponse)
async def get_index_info(
    collection_name: str = "competitor_docs",
) -> CollectionInfoResponse:
    """인덱스 컬렉션 현황(문서 청크 수, 존재 여부)을 조회한다."""
    info = rag_service.get_collection_info(collection_name=collection_name)
    return CollectionInfoResponse(**info)
