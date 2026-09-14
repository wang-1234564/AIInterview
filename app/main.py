"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, init_db
from app.routers import interview, knowledge, profile, settings
from app.services.llm_config import migrate_plaintext_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 把历史遗留的明文 API Key 升级为密文（幂等）
    with SessionLocal() as db:
        migrate_plaintext_key(db)
    yield


app = FastAPI(title="AI 模拟面试智能体", lifespan=lifespan)

# 业务路由
app.include_router(knowledge.router)
app.include_router(interview.router)
app.include_router(profile.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 静态前端（html=True 使 / 直接渲染 index.html）
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
