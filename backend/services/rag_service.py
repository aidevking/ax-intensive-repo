"""
RAG 인덱싱·검색 비즈니스 로직.

역할 경계:
  - 공개 자료(기능 설명, 릴리즈노트, 공개 기사)를 청크 분할·임베딩·인덱싱한다.
  - 질의와 관련된 근거 문서를 검색하여 출처 메타데이터와 함께 반환한다.
  - LLM 호출 및 답변 문장 생성은 하지 않는다. 그 역할은 generate 모듈에 있다.

재인덱싱 주의:
  - chunk_size, chunk_overlap, EMBED_MODEL_NAME 변경 시 기존 인덱스를 삭제하고
    backend/scripts/build_index.py 를 재실행해야 한다.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Optional

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# 상수 — 변경 시 인덱스 재구축 필요
# ---------------------------------------------------------------------------
EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# chromadb 저장 경로 (프로젝트 루트 기준 상대 경로를 절대 경로로 변환)
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTOR_STORE_PATH = str(_PROJECT_ROOT / "backend" / "data" / "vector_store")

# ---------------------------------------------------------------------------
# 싱글턴 임베딩 모델 — 프로세스당 1회 초기화
# ---------------------------------------------------------------------------
_embed_model_instance: Optional[SentenceTransformer] = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model_instance
    if _embed_model_instance is None:
        _embed_model_instance = SentenceTransformer(EMBED_MODEL_NAME)
    return _embed_model_instance


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def _source_hash(source: str) -> str:
    """한글/특수문자 포함 source 문자열을 chromadb ID 안전 ASCII 해시로 변환."""
    return hashlib.md5(source.encode("utf-8")).hexdigest()[:12]


def _make_chunk_id(app_name: str, source: str, chunk_idx: int) -> str:
    """중복 없는 chromadb 문서 ID 생성. ASCII+숫자만 포함."""
    safe_app = hashlib.md5(app_name.encode("utf-8")).hexdigest()[:8]
    safe_src = _source_hash(source)
    return f"{safe_app}_{safe_src}_{chunk_idx}"


# ---------------------------------------------------------------------------
# RagService
# ---------------------------------------------------------------------------

class RagService:
    """경쟁 앱 공개 자료 인덱싱 및 근거 문서 검색 서비스."""

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(path=VECTOR_STORE_PATH)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _get_collection(self, collection_name: str) -> chromadb.Collection:
        """컬렉션을 가져오거나 새로 생성한다. cosine 유사도 공간 사용."""
        return self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _delete_existing_chunks(
        self,
        collection: chromadb.Collection,
        app_name: str,
        source: str,
    ) -> None:
        """동일 app_name + source 의 기존 청크를 모두 삭제해 재인덱싱 시 중복을 방지한다."""
        try:
            existing = collection.get(
                where={"$and": [{"app_name": app_name}, {"source": source}]}
            )
            ids_to_delete = existing.get("ids", [])
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
        except Exception:
            # 컬렉션이 비어있거나 where 절 결과가 없으면 무시
            pass

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def index_documents(
        self,
        documents: list[dict],
        collection_name: str = "competitor_docs",
    ) -> dict:
        """
        공개 자료 문서 목록을 청크 분할·임베딩·인덱싱한다.

        Parameters
        ----------
        documents : list[dict]
            각 dict 는 {"content": str, "app_name": str, "source": str, "date": str|None} 형태.
        collection_name : str
            대상 chromadb 컬렉션 이름.

        Returns
        -------
        dict
            {"status": "ok", "indexed_count": int}  — indexed_count 는 청크 수.
        """
        if not documents:
            return {"status": "error", "indexed_count": 0}

        model = _get_embed_model()
        collection = self._get_collection(collection_name)

        total_chunks = 0

        for doc in documents:
            content: str = doc.get("content", "").strip()
            app_name: str = doc.get("app_name", "unknown")
            source: str = doc.get("source", "unknown")
            date: str = doc.get("date") or ""

            if not content:
                continue

            # 동일 source 기존 청크 삭제 (재인덱싱 지원)
            self._delete_existing_chunks(collection, app_name, source)

            # 청크 분할
            chunks = self._splitter.split_text(content)

            if not chunks:
                continue

            # 임베딩 일괄 생성
            embeddings = model.encode(chunks).tolist()

            ids = [_make_chunk_id(app_name, source, i) for i in range(len(chunks))]
            metadatas = [
                {
                    "app_name": app_name,
                    "source": source,
                    "date": date,
                    "is_public": "true",  # 공개 자료 표시 — 비공식 자료 차단 기준
                }
                for _ in chunks
            ]

            collection.add(
                documents=chunks,
                embeddings=embeddings,
                ids=ids,
                metadatas=metadatas,
            )
            total_chunks += len(chunks)

        return {"status": "ok", "indexed_count": total_chunks}

    def search(
        self,
        query: str,
        top_k: int = 5,
        app_name: Optional[str] = None,
        collection_name: str = "competitor_docs",
    ) -> list[dict]:
        """
        질의와 관련된 공개 자료 청크를 검색하여 출처 메타데이터와 함께 반환한다.

        LLM 호출이나 답변 문장 생성을 하지 않는다.
        출처가 불명확한 문서(is_public != "true")는 결과에서 제외한다.

        Parameters
        ----------
        query : str
            검색 질의문.
        top_k : int
            반환할 최대 결과 수.
        app_name : str | None
            특정 앱으로 결과 필터링. None 이면 전체 검색.
        collection_name : str
            대상 chromadb 컬렉션 이름.

        Returns
        -------
        list[dict]
            [{"content": str, "app_name": str, "source": str, "date": str, "score": float}, ...]
            score 는 코사인 유사도(0~1). 높을수록 관련성 높음.
        """
        try:
            collection = self._client.get_collection(name=collection_name)
        except Exception:
            # 컬렉션이 존재하지 않으면 빈 리스트 반환
            return []

        if collection.count() == 0:
            return []

        model = _get_embed_model()
        query_embedding = model.encode([query]).tolist()

        # app_name 필터 구성
        where_clause = None
        if app_name is not None:
            where_clause = {"app_name": app_name}

        query_kwargs: dict = {
            "query_embeddings": query_embedding,
            "n_results": min(top_k, collection.count()),
        }
        if where_clause is not None:
            query_kwargs["where"] = where_clause

        raw = collection.query(**query_kwargs)

        results: list[dict] = []
        documents_list = raw.get("documents") or [[]]
        metadatas_list = raw.get("metadatas") or [[]]
        distances_list = raw.get("distances") or [[]]

        for doc, meta, dist in zip(
            documents_list[0],
            metadatas_list[0],
            distances_list[0],
        ):
            # 출처 불명확 문서 제외 (공개 자료만 허용)
            if meta.get("is_public") != "true":
                continue

            # 코사인 공간에서 distance ∈ [0, 2]; 유사도로 변환
            score = max(0.0, 1.0 - dist)

            results.append(
                {
                    "content": doc,
                    "app_name": meta.get("app_name", ""),
                    "source": meta.get("source", ""),
                    "date": meta.get("date") or None,
                    "score": score,
                }
            )

        return results

    def get_collection_info(
        self, collection_name: str = "competitor_docs"
    ) -> dict:
        """
        인덱스 현황을 반환한다.

        Returns
        -------
        dict
            {"collection_name": str, "count": int, "exists": bool}
        """
        try:
            collection = self._client.get_collection(name=collection_name)
            return {
                "collection_name": collection_name,
                "count": collection.count(),
                "exists": True,
            }
        except Exception:
            return {
                "collection_name": collection_name,
                "count": 0,
                "exists": False,
            }
