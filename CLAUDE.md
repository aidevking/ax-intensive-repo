# 프로젝트: 신규 금융 앱 출시 초기 고객 반응 및 경쟁 앱 벤치마킹 분석 서비스

신한은행 임직원 교육 과정 프로젝트. 4인 팀 (수집·전처리 / 모델링 / RAG·LLM / 통합·데모).

## 한 줄 요약

앱스토어 공개 리뷰와 경쟁 앱 데이터를 AI가 수집·분석해 핵심 이슈, 고객 감성,
개선 우선순위, 경쟁사 강점을 한 화면에서 제시하는 서비스.

## 절대 원칙 (모든 작업에 적용)

- **실제 고객정보·내부 비공개 데이터 사용 금지.** 공개 리뷰/공개 자료만 사용한다.
- **스크래핑 시 이용약관·robots.txt 준수.** 과도한 요청(rate limit)을 피한다.
- **경쟁 앱 비교는 공개 설명 기준으로만.** 내부 전략을 추정하거나 단정하지 않는다.
  RAG/답변 생성 모듈은 항상 출처가 있는 공개 문서 근거로만 답변을 구성한다.
- 모든 새 기능은 아래 "성공 기준"과 연결지어 검증한다.

## 기술 스택

- 백엔드: **FastAPI** (Python 3.11+, async)
- 프론트엔드: **Streamlit**
- 데이터분석: pandas, numpy, scikit-learn, kiwipiepy (한글 형태소 분석)
- 임베딩/RAG: sentence-transformers, langchain, chromadb
- 시각화: plotly
- 수집: google-play-scraper, app-store-scraper, beautifulsoup4
- 패키지 관리: `pip install -r requirements.txt` (가상환경 사용, `--break-system-packages` 불필요 — 로컬 venv 기준)

## 아키텍처: 4개 모듈

```
Streamlit (프론트엔드)
        │  REST API
        ▼
FastAPI 백엔드
 ├─ 리뷰 수집 모듈        (collect)   — 스토어 리뷰 수집·저장
 ├─ 데이터 분석 모듈      (analyze)   — 감성분류·토픽모델링·EDA
 ├─ 답변 가이드 RAG 모듈  (rag)       — 경쟁사 자료 검색·근거 제공
 └─ 답변 생성 모듈        (generate)  — 분석결과+RAG근거 → 리포트 생성
```

데이터 흐름: `collect` → `analyze` → (`rag` 가 병렬로 근거 검색) → `generate`가 둘을 합쳐 최종 리포트 생성.

## 폴더 구조

```
backend/
  main.py                 # FastAPI 앱 진입점, 라우터 등록
  routers/
    collect.py             # POST /collect/reviews, GET /collect/status/{job_id}
    analyze.py             # POST /analyze/sentiment, GET /analyze/topics, GET /analyze/eda, GET /analyze/metrics
    rag.py                  # POST /rag/index, POST /rag/search
    generate.py             # POST /generate/report
  services/
    collect_service.py
    analyze_service.py
    rag_service.py
    generate_service.py
  schemas/                  # Pydantic 요청/응답 모델 (모듈별 분리)
  data/
    raw/                    # 원본 수집 데이터
    processed/               # 전처리 완료 데이터
    vector_store/             # chromadb persist 디렉토리
frontend/
  app.py                    # Streamlit 진입점
  pages/                     # 멀티페이지 구성 시
  api_client.py               # FastAPI 호출 래퍼
requirements.txt
```

## 모듈 간 계약 (Contract)

새 모듈을 추가하거나 기존 모듈을 수정할 때 이 계약을 깨지 않는다:

- `collect` 모듈의 출력 스키마(앱명, 소스, 리뷰ID, 별점, 작성일, 본문)는 `analyze`/`generate`가
  그대로 소비할 수 있어야 한다. 스키마 변경 시 두 모듈을 함께 업데이트한다.
- `analyze` 모듈은 분류/토픽 결과를 캐싱해서 `generate` 호출마다 재계산하지 않는다.
- `rag` 모듈은 **답변을 생성하지 않는다** — 근거 문서 검색까지만 책임진다. 답변 생성은 `generate`의 역할이다.
- `generate` 모듈은 응답 시간을 로깅한다 (성공 기준 ④ 검증용).

## 성공 기준 (구현 시 항상 참고)

| 기준 | 목표 |
|---|---|
| 리뷰 수집량 | 1,000건 이상 |
| 감성/불만유형 분류 성능 | F1-score 0.75 이상 |
| 주요 토픽 도출 | 5개 이상 |
| 리포트 생성 속도 | 요청 후 30초 이내 |
| 실패/오분류 케이스 분석 | 3건 이상 명시 |

## 코딩 컨벤션

- FastAPI 라우터는 얇게 유지하고 실제 로직은 `services/`에 둔다.
- 모든 엔드포인트는 Pydantic 응답 모델을 명시한다 (`response_model=...`).
- 비동기 I/O가 필요한 수집/외부 호출은 `async def` + `httpx`/`asyncio`를 사용한다.
- 에러는 FastAPI `HTTPException`으로 명확한 상태코드와 메시지를 반환한다.
- 커밋 전 변경된 모듈에 대해 관련 테스트를 실행한다.

## 서브에이전트 사용 가이드

작업 성격에 따라 `.claude/agents/`의 전문 에이전트를 호출한다:

- 리뷰 수집/스크래핑 작업 → `review-collector`
- 감성분석/토픽모델링/EDA → `data-analyst`
- RAG 인덱싱/검색 로직 → `rag-engineer`
- FastAPI 라우터/서비스 설계 전반 → `api-architect`
- Streamlit 화면 작업 → `frontend-builder`
- 성공 기준 검증, 테스트 작성 → `qa-reviewer`

## 스킬 참고

- `.claude/skills/review-scraping` — 스토어 리뷰 수집 시 스키마/약관 준수 규칙
- `.claude/skills/sentiment-topic-modeling` — 라벨링·모델링·평가 방법론
- `.claude/skills/rag-indexing` — 청크/임베딩/인덱싱 규칙과 근거 기반 답변 제약
- `.claude/skills/fastapi-module-pattern` — 라우터/서비스/스키마 3계층 패턴
