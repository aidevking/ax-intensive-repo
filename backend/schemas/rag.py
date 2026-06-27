from pydantic import BaseModel
from typing import Optional


class Document(BaseModel):
    content: str
    app_name: str
    source: str
    date: Optional[str] = None


class IndexRequest(BaseModel):
    documents: list[Document]
    collection_name: str = "competitor_docs"


class IndexResponse(BaseModel):
    status: str
    indexed_count: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    app_name: Optional[str] = None
    collection_name: str = "competitor_docs"


class SearchResult(BaseModel):
    content: str
    app_name: str
    source: str
    date: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    disclaimer: str = (
        "이 결과는 공개 자료 기준이며 내부 전략 추정에 사용하지 말 것."
    )


class CollectionInfoResponse(BaseModel):
    collection_name: str
    count: int
    exists: bool
