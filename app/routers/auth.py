"""登录 / 登出。"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..deps import DbSession
from ..models import User
from ..security import encode_session, verify_password
from ..web import render

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_page(request: Request):
    return render(request, "login.html", user=None)


@router.post("/login")
def login_submit(
    request: Request,
    db: DbSession,
    username: str = Form(""),
    password: str = Form(""),
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if user is None or not verify_password(password, user.password_hash):
        return render(request, "login.html", error="账号或密码不正确", username=username)

    from datetime import datetime

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
