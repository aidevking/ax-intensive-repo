# app-review-analyze

신규 금융 앱 출시 초기 고객 반응 및 경쟁 앱 벤치마킹 분석 서비스입니다.

## 핵심 도메인 스키마

프로젝트는 `app -> review -> review_analysis` 관계를 기준으로 재구성되었습니다.

- `apps`: 앱 메타데이터와 Google Play/App Store 식별자를 저장합니다.
- `reviews`: 스토어 원본 리뷰 ID, 플랫폼, 평점, 버전, 작성자, 본문을 저장합니다.
- `review_analysis`: 감성, 페인포인트, 요약, 키워드, 답변 제안, 처리 상태를 저장합니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 백엔드 | FastAPI, SQLite, Pydantic |
| 프론트엔드 | Next.js App Router, React, TypeScript |
| 분석/RAG | pandas, scikit-learn, sentence-transformers, chromadb |

## 주요 API

```text
POST /reviews/apps                 앱 생성/업서트
GET  /reviews/apps                 앱별 리뷰 카운트 조회
GET  /reviews/apps/{app_key}       앱 상세 조회
POST /reviews/                     리뷰 생성/업서트
GET  /reviews/?app_key=...         앱 리뷰와 분석 결과 통합 조회
POST /reviews/analysis             특정 리뷰 분석 생성/업서트
GET  /reviews/{review_id}/analysis 특정 리뷰의 분석 결과 조회
GET  /reviews/stats/summary        감성/플랫폼/페인포인트 통계 조회
POST /reviews/seed-sample          예시 신한 SOL뱅크 데이터 적재
```

## 실행 방법

### 백엔드

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload
```

LLM 기반 리포트 생성을 사용하려면 `.env`의 `OPENAI_API_KEY` 값을 실제 키로 설정합니다. `.env`는 Git에 포함하지 않습니다.

### 프론트엔드

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

`frontend/.env.example`의 `NEXT_PUBLIC_API_BASE_URL` 기본값은 `http://localhost:8000`이며, 배포/로컬 환경에 맞게 `.env.local`에서 변경할 수 있습니다. 브라우저에서 `http://localhost:3000`으로 접속합니다. 프론트엔드는 자동 mock/seed 데이터를 넣지 않으며, `/reviews`에서 실제 스토어 수집을 실행한 뒤 저장된 데이터를 조회합니다. 기존 Streamlit 프론트엔드 파일은 제거했고 `frontend/app`, `frontend/src` 중심으로 구성합니다.

- `/reviews`: 기간과 플랫폼을 지정해 신한 SOL뱅크 리뷰를 불러오고, 테이블 행 클릭 시 분석 상세 모달과 관리자 답변 복사 버튼을 제공합니다. 스토어 수집 완료 시 리뷰는 `apps` → `reviews` → `review_analysis` 스키마로 저장되어 같은 화면에 표시됩니다.
- `/dashboard`: 일자 단위 기간을 지정해 전체 리뷰 분석, 감성 분포, 고객 Top 3 페인포인트를 확인합니다.

## 테스트/점검

```bash
python -m compileall backend
python - <<'PY'
from fastapi.testclient import TestClient
from backend.main import app
c = TestClient(app)
print(c.post('/reviews/seed-sample').status_code)
print(c.get('/reviews/?app_key=shinhan-sol-bank').json()['total'])
print(c.get('/reviews/stats/summary').json())
PY
```

## 데이터 보관 정책

- 과거 수집 산출물(JSON/parquet)과 임베딩 벡터스토어 파일은 저장소에서 제거했습니다.
- 런타임에서 새로 수집되는 원본 파일은 `backend/data/raw/`에 생성될 수 있지만, 화면 조회 기준 데이터는 SQLite의 `apps`, `reviews`, `review_analysis` 테이블입니다.
