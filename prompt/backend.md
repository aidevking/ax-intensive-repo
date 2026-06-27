# 백엔드 구현 프롬프트 시퀀스 (모듈 단위 + 검증 게이트)

## 사용 방법

1. 클로드 코드를 프로젝트 루트(`CLAUDE.md`, `.claude/`가 있는 위치)에서 실행한다.
2. 아래 프롬프트를 **순서대로** 하나씩 입력한다. 한 단계의 "검증 통과"를 확인하기 전에는
   다음 단계로 넘어가지 않는다.
3. 검증에서 실패가 보고되면, 그 결과를 그대로 클로드 코드에 붙여넣고
   "위 실패 항목을 수정하고 다시 검증해줘"라고 요청한 뒤 같은 단계를 반복한다.
4. 모든 프롬프트에는 "검증이 끝나기 전에는 다음 모듈로 넘어가지 마라"는 지시를 의도적으로
   포함시켰다. 클로드 코드가 검증 없이 다음 작업으로 넘어가려 하면 이 문서의 해당 단계 문구를
   다시 붙여넣어 상기시킨다.

---

## Step 0. 프로젝트 초기 셋업 + 헬스체크

```
CLAUDE.md를 읽고 프로젝트 구조를 파악해줘.
api-architect 에이전트를 사용해서 backend/ 폴더에 FastAPI 프로젝트 뼈대를 구성해줘.

요구사항:
1. backend/main.py - FastAPI 앱 생성, CORS 설정(Streamlit 로컬 접근 허용), 헬스체크 엔드포인트 GET /health 추가
2. backend/routers/, backend/services/, backend/schemas/ 폴더와 각 모듈(collect, analyze, rag, generate)별
   빈 라우터 파일을 생성하고 main.py에 등록 (아직 실제 로직은 구현하지 않음, 라우터는 더미 응답만)
3. requirements.txt 작성 (CLAUDE.md 기술 스택 기준)
4. backend/data/raw, backend/data/processed, backend/data/vector_store 폴더 생성 (.gitkeep 포함)

구현이 끝나면 직접 다음을 검증해줘:
- `uvicorn backend.main:app`으로 서버가 정상 기동되는지
- GET /health 가 200을 반환하는지
- GET /docs (OpenAPI 문서)에 4개 모듈 라우터(collect, analyze, rag, generate)가 모두 노출되는지

검증 결과를 표로 보여줘. 모두 통과하기 전까지는 "Step 0 완료"라고 말하지 마.
```

**검증 게이트:** 서버 기동 / `/health` 200 / `/docs`에 4개 라우터 노출 — 셋 다 통과해야 Step 1로 이동.

---

## Step 1. 리뷰 수집 모듈 (collect)

```
review-collector 에이전트와 review-scraping 스킬을 사용해서
backend/services/collect_service.py, backend/routers/collect.py, backend/schemas/collect.py를 구현해줘.

요구사항:
1. POST /collect/reviews
   - 입력: 앱 목록(app_id, app_name, source, store별 식별자), 수집 기간
   - google-play-scraper / app-store-scraper로 리뷰 수집 후
     review-scraping 스킬에 정의된 스키마(app_id, app_name, source, review_id, rating, review_date,
     review_text, collected_at)로 통일해서 backend/data/raw에 parquet으로 저장
   - 비동기 작업으로 처리하고 job_id 반환
2. GET /collect/status/{job_id}
   - 진행 상태, 수집 건수, 완료 여부 반환
3. (app_id, review_id) 기준 중복 제거 로직 포함
4. 실제 외부 API 호출 실패 시 재시도 2회 + 명확한 에러 메시지

구현 후 다음을 직접 실행해서 검증해줘:
1. pytest 단위 테스트 작성 및 실행: 스키마 정합성, 중복 제거 로직 (외부 API는 모킹)
2. 실제 앱 1개를 대상으로 소량(예: 50건) 수집을 직접 실행해서 결과 스키마가 정의와 일치하는지 확인
3. robots.txt/약관상 문제가 될 수 있는 부분이 있었는지 스스로 점검하고 보고

검증 결과(테스트 통과 여부, 실제 수집 샘플 건수와 스키마 확인 결과)를 표로 정리해줘.
모두 통과하기 전까지는 "Step 1 완료"라고 말하지 말고, 실패 항목이 있으면 무엇을 더 해야
1,000건 이상 수집 목표를 달성할 수 있을지도 함께 알려줘.
```

**검증 게이트:** pytest 통과 / 실제 소량 수집 스키마 일치 / 약관 준수 자가점검 완료 — 셋 다 통과해야 Step 2로 이동.

---

## Step 2. 데이터 분석 모듈 (analyze)

```
data-analyst 에이전트와 sentiment-topic-modeling 스킬을 사용해서
backend/services/analyze_service.py, backend/routers/analyze.py, backend/schemas/analyze.py를 구현해줘.

전제: backend/data/raw에 Step 1에서 저장한 수집 데이터가 있다고 가정한다 (없으면 샘플 데이터를 만들어서
개발/테스트용으로 사용하고, 그 사실을 보고해줘).

요구사항:
1. 전처리 파이프라인: kiwipiepy 형태소 분석, 정제, backend/data/processed 저장
2. 별점 기반 약지도 라벨링 + 별점-텍스트 불일치 샘플 탐지 로직
3. 감성/불만유형 분류 모델 학습 (sentence-transformers + scikit-learn), 모델은 앱 단위로 캐싱
4. 토픽 모델링/키워드 분석 (로그인, 인증, 속도, 혜택, 송금, 투자 등 카테고리 후보)
5. 엔드포인트:
   - POST /analyze/sentiment - 리뷰 배치 받아 감성/불만유형 분류
   - GET /analyze/topics?app_id=... - 토픽 분포 반환
   - GET /analyze/eda?app_id=... - 별점 추이, 리뷰량 등 통계 반환
   - GET /analyze/metrics - 분류 모델 F1-score 등 평가 지표 반환

구현 후 다음을 직접 실행해서 검증해줘:
1. pytest로 전처리/라벨링/분류 로직 단위 테스트
2. 실제(또는 샘플) 데이터로 모델을 학습시키고 macro F1-score를 측정 - 0.75 미달이면
   원인(클래스 불균형, 데이터 부족 등)을 분석하고 시도한 개선책을 보고
3. 토픽이 5개 이상 도출되는지 확인, 각 토픽의 대표 키워드 예시 제시
4. 오분류 케이스 3건 이상을 선별해서 원인 기록 (성공 기준 ⑤)

검증 결과(F1-score 수치, 토픽 개수, 오분류 케이스 목록)를 표/목록으로 정리해줘.
F1-score, 토픽 개수, 오분류 케이스 기록이 모두 기준을 충족하기 전까지는
"Step 2 완료"라고 말하지 마.
```

**검증 게이트:** pytest 통과 / macro F1 ≥ 0.75 (또는 미달 원인·개선 시도 명시) / 토픽 5개 이상 / 오분류 케이스 3건 이상 — 모두 충족해야 Step 3으로 이동.

---

## Step 3. 답변 가이드 RAG 모듈 (rag)

```
rag-engineer 에이전트와 rag-indexing 스킬을 사용해서
backend/services/rag_service.py, backend/routers/rag.py, backend/schemas/rag.py를 구현해줘.

요구사항:
1. POST /rag/index
   - 경쟁 앱 공개 기능설명/릴리즈노트/기사 문서를 받아 청크 분할 → 임베딩 → chromadb 인덱싱
   - 메타데이터(app_name, source, date)를 반드시 포함
2. POST /rag/search
   - 질의를 받아 관련 문서(근거)만 반환한다. **답변 문장을 생성하지 않는다** (rag-indexing 스킬의
     역할 경계를 반드시 지킨다 - 이 모듈은 generate 모듈이 아니다)
   - 각 검색 결과에 출처 메타데이터 포함

구현 후 다음을 직접 실행해서 검증해줘:
1. pytest로 청크 분할/인덱싱 로직 단위 테스트
2. 샘플 문서 3~5건을 인덱싱한 뒤, 관련 질의 2~3개로 검색을 실제 실행해서
   - 검색 결과가 질의와 의미적으로 관련 있는지
   - 모든 결과에 출처 메타데이터가 빠짐없이 포함되는지
   - 검색 응답 속도가 충분히 빠른지(목표: 수 초 이내, 전체 30초 예산 중 일부임을 감안)
3. 이 모듈이 답변 문장을 생성하지 않고 근거만 반환하는지(역할 경계 위반 없는지) 코드 리뷰 관점에서
   스스로 점검

검증 결과를 표로 정리해줘. 모두 통과하기 전까지는 "Step 3 완료"라고 말하지 마.
```

**검증 게이트:** pytest 통과 / 검색 결과 관련성·출처 메타데이터 확인 / 역할 경계(답변 미생성) 자가점검 통과 — 모두 충족해야 Step 4로 이동.

---

## Step 4. 답변 생성 모듈 (generate)

```
api-architect 에이전트를 사용해서
backend/services/generate_service.py, backend/routers/generate.py, backend/schemas/generate.py를 구현해줘.

요구사항:
1. POST /generate/report
   - 입력: app_id
   - analyze 모듈의 결과(주요 불만 토픽, 감성 분포)와 rag 모듈의 검색 결과(경쟁사 근거 문서)를
     합쳐서 LLM 호출로 요약 리포트 생성
   - 프롬프트에 "공개 자료 근거만 사용, 내부 전략 추정 금지"를 명시적으로 포함 (CLAUDE.md 절대 원칙)
   - 응답에 사용한 근거 문서 출처를 함께 포함시켜 추적 가능하게 한다
2. 요청 처리 시간을 로깅하고, 응답에 처리 소요 시간(ms)을 포함시킨다

구현 후 다음을 직접 실행해서 검증해줘:
1. pytest로 입력 결합 로직(분석 결과 + RAG 근거 → 프롬프트 구성) 단위 테스트 (LLM 호출은 모킹)
2. 실제(또는 샘플) app_id로 엔드투엔드 호출을 실행해서
   - 응답 시간이 30초 이내인지 측정
   - 리포트 내용에 출처가 명시되어 있는지
   - 내부 전략을 추정하는 듯한 단정적 표현이 없는지 직접 점검
3. 위 세 가지 중 하나라도 기준 미달이면 원인과 시도한 조치를 보고

검증 결과를 표로 정리해줘. 모두 통과하기 전까지는 "Step 4 완료"라고 말하지 마.
```

**검증 게이트:** pytest 통과 / 응답시간 30초 이내 / 출처 명시 / 절대 원칙(내부전략 추정 금지) 위반 없음 — 모두 충족해야 Step 5로 이동.

---

## Step 5. 통합 검증 (e2e + 성공 기준 종합 점검)

```
qa-reviewer 에이전트를 사용해서 전체 백엔드를 종합 점검해줘.

요구사항:
1. collect → analyze → rag → generate 전체 흐름을 실제로 한 번 e2e로 실행
2. CLAUDE.md의 성공 기준 표를 기준으로 다음을 모두 점검하고 결과를 표로 보고:
   - 리뷰 수집량 1,000건 이상
   - 분류 성능 F1-score 0.75 이상
   - 주요 토픽 5개 이상
   - 리포트 생성 속도 30초 이내
   - 오분류/실패 케이스 3건 이상 기록
3. 절대 원칙 위반 여부(실제 고객정보 미사용, 약관 준수, 내부 전략 추정 금지) 코드 전반 재점검
4. 미충족 항목이 있으면 어느 모듈/파일을 더 손봐야 하는지 구체적으로 짚어줘

이 단계 보고가 끝나기 전까지 "백엔드 구현 완료"라고 말하지 마. 미충족 항목이 있으면
그 항목만 콕 집어서 "이 부분을 보완해줘"라고 다시 요청할 수 있도록 목록으로 정리해줘.
```

**검증 게이트:** 성공 기준 5개 항목 전부 + 절대 원칙 위반 없음 — 모두 충족해야 백엔드 구현 완료로 간주.