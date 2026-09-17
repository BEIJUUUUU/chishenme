"""登录 / 登出。

默认是免登录模式（auth_mode='none'）：家里局域网自用，打开网页直接就是管理员，
没有任何账号密码要记。「设置 → 访问控制」可以切成需要账号密码。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..deps import DbSession, auth_mode
from ..models import User
from ..security import encode_session, verify_password
from ..web import render

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_page(request: Request, db: DbSession):
    # 免登录模式没有登录页，直接进首页
    if auth_mode(db) != "password":
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html", user=None)


@router.post("/login")
def login_submit(
    request: Request,
    db: DbSession,
    username: str = Form(""),
    password: str = Form(""),
):
    if auth_mode(db) != "password":
        return RedirectResponse("/dashboard", status_code=303)

    user = db.query(User).filter(User.username == username.strip()).first()
    if user is None or not verify_password(password, user.password_hash):
        return render(request, "login.html", error="账号或密码不正确", username=username)

    user.last_login_at = datetime.now()
    db.commit()

    settings = get_settings()
    token = encode_session({"uid": user.id, "name": user.username})
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
def logout(request: Request):
    settings = get_settings()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.session_cookie)
    return response
