from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # .env → os.environ (서비스 import 전에 실행)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import reviews

optional_routers = []
for module_name, prefix, tag in [
    ("collect", "/collect", "collect"),
    ("analyze", "/analyze", "analyze"),
    ("rag", "/rag", "rag"),
    ("generate", "/generate", "generate"),
]:
    try:
        module = __import__(f"backend.routers.{module_name}", fromlist=["router"])
        optional_routers.append((module.router, prefix, tag))
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.services import db_service
    db_service.init_db()
    yield


app = FastAPI(
    title="App Review Analyzer",
    description="신규 금융 앱 출시 초기 고객 반응 및 경쟁 앱 벤치마킹 분석 서비스",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)

for router, prefix, tag in optional_routers:
    app.include_router(router, prefix=prefix, tags=[tag])
app.include_router(reviews.router, prefix="/reviews", tags=["reviews"])


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}
