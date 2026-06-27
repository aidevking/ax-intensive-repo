"""
backend/scripts/build_index.py

경쟁 앱 공개 자료를 chromadb에 (재)인덱싱하는 스크립트.

사용 방법:
    python backend/scripts/build_index.py
    python backend/scripts/build_index.py --source backend/data/raw/competitor_docs.json
    python backend/scripts/build_index.py --collection my_collection --rebuild

재인덱싱이 필요한 경우:
  - EMBED_MODEL_NAME 변경 시
  - CHUNK_SIZE / CHUNK_OVERLAP 변경 시
  - 원본 문서가 갱신된 경우

--rebuild 플래그를 사용하면 컬렉션을 완전히 삭제 후 재구축한다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.services.rag_service import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBED_MODEL_NAME,
    VECTOR_STORE_PATH,
    RagService,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="경쟁 앱 공개 자료 RAG 인덱싱 스크립트")
    parser.add_argument(
        "--source",
        default=str(_ROOT / "backend" / "data" / "raw" / "competitor_docs.json"),
        help="인덱싱할 JSON 파일 경로 (기본값: backend/data/raw/competitor_docs.json)",
    )
    parser.add_argument(
        "--collection",
        default="competitor_docs",
        help="chromadb 컬렉션 이름 (기본값: competitor_docs)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="컬렉션을 완전히 삭제 후 재구축 (chunk_size/model 변경 시 사용)",
    )
    args = parser.parse_args()

    print(f"[설정]")
    print(f"  임베딩 모델  : {EMBED_MODEL_NAME}")
    print(f"  청크 크기    : {CHUNK_SIZE} / 오버랩: {CHUNK_OVERLAP}")
    print(f"  벡터 스토어  : {VECTOR_STORE_PATH}")
    print(f"  컬렉션       : {args.collection}")
    print(f"  소스 파일    : {args.source}")
    print()

    source_path = pathlib.Path(args.source)
    if not source_path.exists():
        print(f"[오류] 파일이 존재하지 않습니다: {source_path}")
        sys.exit(1)

    with open(source_path, encoding="utf-8") as f:
        docs = json.load(f)

    print(f"[로드] {len(docs)}개 문서 로드 완료")

    svc = RagService()

    if args.rebuild:
        try:
            svc._client.delete_collection(args.collection)
            print(f"[재구축] 기존 컬렉션 '{args.collection}' 삭제 완료")
        except Exception:
            print(f"[재구축] 컬렉션이 존재하지 않아 삭제 생략")

    result = svc.index_documents(docs, collection_name=args.collection)

    if result["status"] == "ok":
        print(f"[완료] indexed_count={result['indexed_count']} 청크 인덱싱 성공")
        info = svc.get_collection_info(args.collection)
        print(f"[현황] 컬렉션 총 청크 수: {info['count']}")
    else:
        print(f"[오류] 인덱싱 실패: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
