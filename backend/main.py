# 0724 FastAPI 应用入口 — 客诉系统 v3.5.0 后端
"""AI 客诉处理系统 — FastAPI 后端入口"""

import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from data.database import init_db, init_users
from core.smtp_config import reload_smtp_config
from core.dingtalk_config import reload_dingtalk_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库。"""
    init_db()
    init_users()
    reload_smtp_config()   # 0811 DB 优先加载 SMTP 配置
    reload_dingtalk_config()  # 0824 DB 优先加载钉钉通知配置
    yield


app = FastAPI(
    title="AI 客诉处理系统 API",
    description="客诉管理系统 v3.5.0 — FastAPI 后端",
    version="3.5.0",
    lifespan=lifespan,
)

# CORS — 开发环境放开所有来源（多前端并发 + 局域网共享）
# 生产部署时改为具体的域名列表
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "ok", "version": "3.5.0"}


# 0724 路由注册（各模块在后续阶段逐步注册）
from api.auth import router as auth_router
from api.complaints import router as complaints_router
from api.files import router as files_router
from api.websocket import router as websocket_router
from api.knowledge import router as knowledge_router
from api.notifications import router as notifications_router
from api.analytics import router as analytics_router
from api.ai import router as ai_router
from api.users import router as users_router
from api.feedback import router as feedback_router
from api.eval import router as eval_router
from api.settings import router as settings_router
from api.export import router as export_router
from api.batch_import import router as batch_import_router

app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
app.include_router(complaints_router, prefix="/api/complaints", tags=["投诉"])
app.include_router(files_router, prefix="/api/files", tags=["附件"])
app.include_router(websocket_router, prefix="/api", tags=["实时推送"])
app.include_router(knowledge_router, prefix="/api/knowledge", tags=["知识库"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["通知中心"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["分析看板"])
app.include_router(ai_router, prefix="/api/ai", tags=["AI 智能"])
app.include_router(users_router, prefix="/api/users", tags=["用户管理"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["用户评价"])
app.include_router(eval_router, prefix="/api/eval", tags=["系统评估"])
app.include_router(settings_router, prefix="/api/settings", tags=["系统设置"])
app.include_router(export_router, prefix="/api/export", tags=["数据导出"])
app.include_router(batch_import_router, prefix="/api/batch-import", tags=["批量导入"])

# 0727 生产部署：单进程同时服务前端静态文件 + 后端 API
# 前端构建到 frontend/dist/，后端直接 serve，无需单独启动 Vite
# uvicorn 的异步机制自动处理多用户并发，无需每人一个终端
STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if STATIC_DIR.is_dir():
    # 挂载静态资源（JS/CSS/图片等），不设 html=True，避免与 SPA 路由冲突
    # 0728 JS/CSS 文件名含 hash（Vite 构建自动生成），设长缓存提升性能；index.html 通过 SPA fallback 返回并设 no-cache
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # favicon
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        fav = STATIC_DIR / "favicon.svg"
        if fav.is_file():
            return FileResponse(fav)
        return HTMLResponse(status_code=404)

    # SPA 回退：所有非 /api/ 的非静态请求返回 index.html
    # 必须放在最后注册，这样 API 路由优先匹配
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str):
        """SPA fallback — 将前端路由交由 Vue Router 处理"""
        # 0819 未注册的 /api/ 路径不应返回前端页面，否则浏览器会把 index.html
        # 误存为下载文件（曾导致导出接口拼写/未更新时下载到 1KB 假 ZIP）
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")
        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        return HTMLResponse(content="<h1>前端未构建</h1><p>请运行 npm run build</p>", status_code=404)

    # 根路径明确注册，确保首页优先返回
    @app.get("/", include_in_schema=False)
    async def root():
        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        return HTMLResponse(content="<h1>前端未构建</h1><p>请运行 npm run build</p>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8506, reload=True)
