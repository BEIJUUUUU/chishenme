"""FastAPI 应用装配。"""
from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .config import get_settings
from .db import init_db, session_scope
from .deps import NotAuthenticated
from .models import Dish, User
from .routers import api, auth, dishes, pages, settings_router
from .runtime_config import load_config
from .scheduler import scheduler
from .security import hash_password
from .version import VERSION
from .web import STATIC_DIR

settings = get_settings()


def setup_logging() -> None:
    settings.ensure_dirs()
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def bootstrap() -> None:
    """首次启动：建管理员、导入内置菜谱。"""
    from .core.pantry import seed_database

    with session_scope() as db:
        user_count = db.execute(select(func.count()).select_from(User)).scalar_one()
        if user_count == 0:
            db.add(
                User(
                    username=settings.admin_user,
                    password_hash=hash_password(settings.admin_password),
                    display_name="管理员",
                )
            )
            logging.getLogger("chishenme").info(
                "已创建管理员账号：%s（请尽快在设置页修改密码）", settings.admin_user
            )

        dish_count = db.execute(select(func.count()).select_from(Dish)).scalar_one()
        if dish_count == 0:
            added = seed_database(db)
            logging.getLogger("chishenme").info("已导入内置菜谱 %s 道", added)

        load_config(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log = logging.getLogger("chishenme")
    init_db()
    bootstrap()
    try:
        scheduler.start()
    except Exception:
        log.exception("调度器启动失败，Web 界面仍可正常使用")

    log.info("%s v%s 已就绪 → http://127.0.0.1:%s", settings.app_name, VERSION, settings.port)
    yield
    scheduler.shutdown()


app = FastAPI(
    title=f"{settings.app_name} API",
    version=VERSION,
    description="家庭中晚餐菜谱生成与微信推送机器人",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(settings_router.router)
app.include_router(dishes.router)
app.include_router(api.router)


@app.exception_handler(NotAuthenticated)
async def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "detail": "未登录"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(404)
async def handle_404(request: Request, exc):
    from fastapi.responses import HTMLResponse

    body = "<h1>页面不存在</h1><p>地址可能写错了，<a href='/dashboard'>回到首页</a></p>"
    return HTMLResponse(body, status_code=404)
