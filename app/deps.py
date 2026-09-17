"""FastAPI 依赖：数据库、当前登录用户、运行期配置。"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
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


def current_user(request: Request, db: DbSession) -> User | None:
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
    from fastapi import HTTPException

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
