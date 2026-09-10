"""sing-box 管理面板 - FastAPI 主入口（纯 JSON API + SPA 托管）"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .models.database import init_db
from .routers import auth, nodes, subscription, api

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CONFIG_DIR = DATA_DIR / "config"
SUB_DIR = DATA_DIR / "sub"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SUB_DIR.mkdir(parents=True, exist_ok=True)

# 前端构建产物目录（生产环境由多阶段 Dockerfile 拷入）
STATIC_DIR = Path(os.getenv("STATIC_DIR", "/app/static"))

app = FastAPI(title="sing-box Panel", version="2.1.0")

app.include_router(auth.router, prefix="/auth", tags=["认证"])
app.include_router(nodes.router, prefix="/nodes", tags=["节点管理"])
app.include_router(subscription.router, prefix="/sub", tags=["订阅"])
app.include_router(api.router, prefix="/api", tags=["API"])


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── 静态文件托管（生产环境） ─────────────────────────────
# 开发环境前端跑在 vite dev server，不挂载；生产环境 dist 拷到 STATIC_DIR
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA 路由兜底：非 API 路径一律返回 index.html，由 Vue Router 接管"""
        # 静态资源（favicon 等）直接返回文件，否则回退到 index.html
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "前端未构建"}, status_code=404)
