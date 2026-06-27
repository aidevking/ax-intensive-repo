"""프론트엔드 공용 상수 모듈

여러 페이지에서 공유하는 앱 표시명, 색상, 감성 라벨 등을 한 곳에서 관리한다.
"""

OWN_APP_ID: str = "com.shinhan.sbanking"

APP_NAME_MAP: dict[str, str] = {
    "com.shinhan.sbanking":  "신한 SOL",
    "com.kbankwith.kbank":   "케이뱅크",
    "com.kakaobank.channel": "카카오뱅크",
    "com.ibk.nhbank":        "NH스마트뱅킹",
    "com.wooribank.pib.dla": "우리WON뱅킹",
}

APP_COLORS: dict[str, str] = {
    "com.shinhan.sbanking":  "#0066CC",
    "com.kbankwith.kbank":   "#FF6600",
    "com.kakaobank.channel": "#FEE500",
    "com.ibk.nhbank":        "#009900",
    "com.wooribank.pib.dla": "#CC0000",
}
DEFAULT_COLOR: str = "#888888"

SENTIMENT_COLORS: dict[str, str] = {
    "positive": "#2ECC71",
    "negative": "#E74C3C",
    "neutral":  "#F39C12",
}

SENTIMENT_LABELS: dict[str, str] = {
    "positive": "긍정",
    "negative": "부정",
    "neutral":  "중립",
}


def app_label(app_id: str) -> str:
    """앱 ID를 한글 표시 이름으로 변환한다. 자사 앱은 (자사)를 붙인다."""
    name = APP_NAME_MAP.get(app_id, app_id)
    return f"{name} (자사)" if app_id == OWN_APP_ID else name
