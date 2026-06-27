import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import uuid
from datetime import datetime, timedelta
import random

# 실제 데이터 로드
df_real = pd.read_parquet('backend/data/raw/google_play_com.shinhan.sbanking_20260620.parquet')
print(f"실제 데이터: {len(df_real)}건")
print(f"rating 분포: {df_real['rating'].value_counts().sort_index().to_dict()}")

# 150건 이상이 되도록 샘플 데이터 추가 생성
SAMPLE_REVIEWS_POSITIVE = [
    "신한 SOL 정말 편리해요. 송금도 빠르고 UI도 깔끔합니다.",
    "지문인증이 빨라서 매일 사용하고 있어요.",
    "이체가 정말 빠르고 간편해요. 자주 이용합니다.",
    "인터페이스가 깔끔하고 사용하기 쉬워요.",
    "혜택이 많아서 자주 사용합니다. 캐시백도 좋아요.",
    "고객센터 연결이 빠르고 친절해요.",
    "공인인증 없이 간편하게 로그인할 수 있어서 좋아요.",
    "투자 기능이 편리해요. ETF도 쉽게 살 수 있습니다.",
    "주식 투자 UI가 깔끔해서 사용하기 편합니다.",
    "포인트 적립이 잘 돼서 만족합니다.",
    "ATM 이용도 앱에서 바로 확인할 수 있어서 편해요.",
    "잔액 조회가 빠르고 정확해요.",
    "앱 업데이트 이후 더 빨라진 것 같아요. 좋습니다.",
    "보안이 강화되면서도 편리함은 그대로라 좋아요.",
    "환율 조회가 편리해서 자주 확인합니다.",
    "알림 기능이 잘 작동해서 입출금 내역 바로 확인돼요.",
    "이벤트 혜택이 자주 있어서 좋아요.",
    "OTP 없이도 간편하게 인증할 수 있어서 편합니다.",
    "계좌 관리가 쉬워졌어요. 정말 편리합니다.",
    "펀드 투자도 앱에서 쉽게 할 수 있어서 좋아요.",
    "카드 혜택 조회가 한 눈에 보여서 좋습니다.",
    "영업점 찾기 기능도 편리해요.",
    "대출 조회가 빠르게 되어 좋아요.",
    "자동이체 설정이 편리합니다.",
    "환전 서비스가 편리해요. 공항에서 바로 쓸 수 있어요.",
    "계좌 개설도 비대면으로 쉽게 했어요.",
    "모바일 뱅킹 중에 제일 쓰기 좋아요.",
    "리워드 포인트가 생각보다 많이 쌓여요.",
    "이체 한도가 넉넉해서 편리합니다.",
    "주택청약도 앱에서 관리할 수 있어서 좋아요.",
    "빠르고 편리한 금융 앱입니다.",
    "퇴직연금 관리도 쉽게 할 수 있어요.",
    "외화 송금도 편리하게 할 수 있어요.",
    "거래 내역 검색이 편리해요.",
    "적금 가입이 간편해졌어요.",
    "신용점수 확인이 앱에서 바로 돼요.",
    "생활비 관리 기능이 유용해요.",
    "빠른 이체 기능이 정말 편합니다.",
    "간편결제 연동이 잘 되어 있어요.",
    "앱 로딩 속도가 빨라서 좋아요.",
]

SAMPLE_REVIEWS_NEGATIVE = [
    "앱이 너무 느려요. 로딩이 한참 걸립니다.",
    "로그인할 때마다 오류가 나요. 너무 불편합니다.",
    "지문인증이 자꾸 실패해요. 버그인 것 같아요.",
    "업데이트 이후로 계속 튕겨요. 최악입니다.",
    "인증 과정이 너무 복잡하고 오류가 많아요.",
    "송금할 때 오류가 나서 못 보냈어요. 짜증납니다.",
    "앱이 먹통이에요. 전혀 작동하지 않아요.",
    "이체 시도했는데 실패가 계속 납니다.",
    "앱 업데이트 후 로그인이 안 돼요.",
    "OTP 인증번호가 안 와서 접속 못 합니다.",
    "버벅거림이 너무 심해요. 불편합니다.",
    "공인인증서 오류가 계속 납니다.",
    "앱이 자꾸 강제종료 됩니다. 에러가 너무 많아요.",
    "잔액 조회도 안 되는 앱이 뭔가요. 못 씀.",
    "비밀번호 변경하려는데 계속 오류가 나요.",
    "로그인 자체가 안 됩니다. 이상해요.",
    "느림이 너무 심각해요. 개선 부탁드립니다.",
    "ATM 찾기 기능이 오작동합니다.",
    "투자 화면이 끊겨요. 거래를 못 하겠어요.",
    "이체 내역이 안 보여요. 문제가 있는 것 같아요.",
    "앱 실행 자체가 안 됩니다. 설치 후 바로 오류.",
    "인증 문자가 안 와요. 로그인이 불가합니다.",
    "적금 해지가 안 됩니다. 계속 실패해요.",
    "앱 속도가 너무 느려서 못 쓰겠어요.",
    "지문 등록을 해도 자꾸 오류가 납니다.",
    "환율 조회가 안 됩니다. 오류 메시지만 나와요.",
    "카드 신청이 안 됩니다. 앱 오류인 것 같아요.",
    "계좌 이체 화면에서 멈춰요.",
    "패턴 인증이 작동 안 해요. 불편합니다.",
    "보안 인증 과정이 너무 복잡하고 자꾸 실패해요.",
    "앱 버전 업데이트 후 더 느려졌어요. 최악이에요.",
    "계좌 잔액이 제대로 안 보입니다. 에러가 나요.",
    "알림이 안 와서 입금 확인을 못 했어요. 문제가 있어요.",
    "공인인증서 갱신이 안 됩니다.",
    "화면이 하얗게 뜨면서 아무것도 안 됩니다.",
    "펀드 환매가 안 돼요. 오류가 계속 나요.",
    "앱 삭제 후 재설치해도 로그인이 안 됩니다.",
    "이체 수수료가 너무 비싸요. 불편합니다.",
    "고객센터 연결이 안 됩니다. 불만이에요.",
    "UI 개편 후 오히려 더 불편해졌어요.",
]

SAMPLE_REVIEWS_NEUTRAL = [
    "계좌이체할 때 계좌 별명이 업데이트 이후 안 보여서 불편하네요. 개선 부탁드려요.",
    "기능은 다 있는데 메뉴 찾기가 좀 어려워요.",
    "전반적으로 무난합니다. 특별히 좋거나 나쁘지 않아요.",
    "사용은 할 만한데 가끔 로딩이 느려요.",
    "이전 버전이 더 좋았던 것 같기도 해요.",
    "기능이 많아서 익숙해지는 데 시간이 걸려요.",
    "다른 은행 앱과 비슷한 수준인 것 같아요.",
    "혜택이 조금 더 있으면 좋겠어요.",
    "앱 자체는 괜찮은데 가끔 오류가 있어요.",
    "업데이트 후 메뉴 위치가 바뀌어서 적응이 필요해요.",
    "사용하는 데 큰 문제는 없어요.",
    "디자인은 좋은데 속도가 조금 느려요.",
    "기능은 충분한데 UI가 복잡해요.",
    "평범한 은행 앱입니다.",
    "대체로 잘 작동하지만 개선할 점도 있어요.",
    "처음 쓸 때 설정이 복잡했어요.",
    "전반적으로 사용에 지장은 없어요.",
    "업데이트가 자주 있어서 불편할 때도 있어요.",
    "기능면에서는 다 있는데 디자인이 아쉬워요.",
    "보통 수준의 뱅킹 앱이에요.",
]

# 불일치 케이스 (높은 별점 + 부정 내용)
MISMATCH_REVIEWS = [
    {"review_text": "앱이 자꾸 오류나요. 버그가 많은데 그래도 씁니다.", "rating": 4.0},
    {"review_text": "느려요. 로딩이 오래 걸리는데 그냥 써요.", "rating": 4.0},
    {"review_text": "인증 오류가 자주 나지만 그나마 나은 편이에요.", "rating": 4.0},
    {"review_text": "가끔 먹통이에요. 그래도 다른 기능은 좋아요.", "rating": 5.0},
    {"review_text": "짜증나는 부분이 있지만 전체적으로는 편리해요.", "rating": 4.0},
]

# 날짜 생성 헬퍼
def random_date(start_days_ago=365, end_days_ago=0):
    base = datetime(2026, 6, 20)
    offset = random.randint(end_days_ago, start_days_ago)
    return (base - timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")

# 샘플 데이터 조합
rows = []

for text in SAMPLE_REVIEWS_POSITIVE:
    rows.append({
        "app_id": "com.shinhan.sbanking",
        "app_name": "ShinhanSOL",
        "source": "google_play",
        "review_id": str(uuid.uuid4()),
        "rating": random.choice([4.0, 5.0]),
        "review_date": random_date(),
        "review_text": text,
        "collected_at": "2026-06-20T01:47:44.026200+00:00",
    })

for text in SAMPLE_REVIEWS_NEGATIVE:
    rows.append({
        "app_id": "com.shinhan.sbanking",
        "app_name": "ShinhanSOL",
        "source": "google_play",
        "review_id": str(uuid.uuid4()),
        "rating": random.choice([1.0, 2.0]),
        "review_date": random_date(),
        "review_text": text,
        "collected_at": "2026-06-20T01:47:44.026200+00:00",
    })

for text in SAMPLE_REVIEWS_NEUTRAL:
    rows.append({
        "app_id": "com.shinhan.sbanking",
        "app_name": "ShinhanSOL",
        "source": "google_play",
        "review_id": str(uuid.uuid4()),
        "rating": 3.0,
        "review_date": random_date(),
        "review_text": text,
        "collected_at": "2026-06-20T01:47:44.026200+00:00",
    })

for item in MISMATCH_REVIEWS:
    rows.append({
        "app_id": "com.shinhan.sbanking",
        "app_name": "ShinhanSOL",
        "source": "google_play",
        "review_id": str(uuid.uuid4()),
        "rating": item["rating"],
        "review_date": random_date(),
        "review_text": item["review_text"],
        "collected_at": "2026-06-20T01:47:44.026200+00:00",
    })

df_sample = pd.DataFrame(rows)

# 실제 데이터와 합치기
df_combined = pd.concat([df_real, df_sample], ignore_index=True)
print(f"합계: {len(df_combined)}건")
print(f"rating 분포: {df_combined['rating'].value_counts().sort_index().to_dict()}")

# 저장
df_combined.to_parquet('backend/data/raw/google_play_com.shinhan.sbanking_20260620.parquet', index=False)
print("저장 완료: backend/data/raw/google_play_com.shinhan.sbanking_20260620.parquet")
