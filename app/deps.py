"""FastAPI 依赖：数据库、当前用户、运行期配置。"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import User
from .runtime_config import AppConfig, load_config
from .security import decode_session

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class NotAuthenticated(Exception):
    """未登录时重定向到登录页。"""


def auth_mode(db: Session) -> str:
    """当前访问模式：none（免登录，默认）或 password。

    环境变量 CSM_AUTH_MODE 可以强制覆盖，方便公网部署时锁死。
    """
    override = (get_settings().auth_mode or "").strip()
    if override in ("none", "password"):
        return override
    return load_config(db).auth_mode


def default_user(db: Session) -> User | None:
    """免登录模式下，把第一个用户当作当前用户（首次启动会自动创建 admin）。"""
    return db.execute(select(User).order_by(User.id)).scalars().first()


def current_user(request: Request, db: DbSession) -> User | None:
    # 免登录模式：打开即用，不校验任何凭据
    if auth_mode(db) != "password":
        return default_user(db)

    token = request.cookies.get(get_settings().session_cookie)
    if not token:
        return None
    payload = decode_session(token)
    if not payload:
        return None
    user_id = payload.get("uid")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: DbSession) -> User:
    """页面路由用：未登录直接抛重定向。"""
    user = current_user(request, db)
    if user is None:
        raise NotAuthenticated()
    return user


def require_user_api(request: Request, db: DbSession) -> User:
    """JSON 接口用：未登录返回 401。"""
    user = current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
CurrentUserApi = Annotated[User, Depends(require_user_api)]


def app_config(db: DbSession) -> AppConfig:
    return load_config(db)


AppConfigDep = Annotated[AppConfig, Depends(app_config)]


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)
