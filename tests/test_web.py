"""Web 层冒烟测试：免登录（默认）、需要登录两种模式、页面渲染、JSON 接口。"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.db import init_db
    from app.main import app, bootstrap

    init_db()
    bootstrap()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_client(client):
    """需要登录模式下，先登录再返回客户端。"""
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "test1234"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    return client


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# 默认：免登录，打开即用
# ---------------------------------------------------------------------------
def test_dashboard_opens_without_login(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "今天吃什么" in resp.text


def test_login_page_redirects_when_auth_disabled(client):
    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_api_opens_without_login(client):
    resp = client.get("/api/plans/2024-07-10")
    assert resp.status_code == 200
    assert resp.json()["date"] == "2024-07-10"


def test_all_pages_open_without_login(client):
    for path in ("/plans", "/settings", "/dishes", "/logs"):
        assert client.get(path).status_code == 200, path


# ---------------------------------------------------------------------------
# 可选：需要账号密码
# ---------------------------------------------------------------------------
def test_password_mode_blocks_anonymous(client, password_mode):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"

    assert client.get("/api/plans/2024-07-10").status_code == 401
    assert client.get("/login").status_code == 200


def test_password_mode_login_flow(client, password_mode):
    bad = client.post(
        "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
    )
    assert bad.status_code == 200
    assert "不正确" in bad.text

    good = client.post(
        "/login",
        data={"username": "admin", "password": "test1234"},
        follow_redirects=False,
    )
    assert good.status_code == 303
    assert client.get("/dashboard").status_code == 200

    assert client.get("/logout", follow_redirects=False).status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


# ---------------------------------------------------------------------------
# 设置与菜谱库
# ---------------------------------------------------------------------------
def test_settings_page_renders(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "家庭画像" in resp.text
    assert "企业微信机器人" in resp.text
    assert "访问控制" in resp.text


def test_settings_save_roundtrip(client):
    resp = client.post(
        "/settings",
        data={
            "auth_mode": "none",
            "family_name": "老王家",
            "province": "四川",
            "city": "成都",
            "people": "5",
            "lunch_count": "4",
            "dinner_count": "4",
            "staple": "米饭",
            "spicy": "1",
            "budget": "80",
            "llm_mode": "off",
            "openai_base_url": "https://api.deepseek.com/v1",
            "openai_model": "deepseek-chat",
            "llm_temperature": "0.8",
            "llm_timeout": "120",
            "llm_max_repair": "2",
            "repeat_window_days": "5",
            "lunch_push_time": "07:30",
            "dinner_push_time": "15:30",
            "push_days_ahead": "0",
            "push_channels": ["wecom"],
            "health_flags": ["高血压"],
            "scheduler_enabled": "on",
            "include_soup": "on",
            "require_meat_and_veg": "on",
            "strict_season": "on",
            "llm_json_mode": "on",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    from app.db import SessionLocal
    from app.runtime_config import load_config, update_config

    db = SessionLocal()
    saved = load_config(db)
    assert saved.family_name == "老王家"
    assert saved.province == "四川"
    assert saved.health_flags == ["高血压"]
    assert saved.push_channels == ["wecom"]
    # 恢复默认，免得影响其他用例
    update_config(db, {"family_name": "我家", "province": "山东", "push_channels": [], "health_flags": []})
    db.close()

    page = client.get("/settings")
    assert page.status_code == 200


def test_dishes_page_and_seed(client):
    client.post("/dishes/seed", follow_redirects=False)
    resp = client.get("/dishes")
    assert resp.status_code == 200
    assert "菜谱库" in resp.text


def test_generate_api_uses_local_library_when_no_llm(client):
    """默认不配大模型时不应 500，也不能卡住重试，而是直接走本地菜谱库。"""
    resp = client.post(
        "/api/generate",
        json={"target_date": "2024-07-11", "meals": ["午餐"], "force": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["results"]["午餐"]["status"] in ("ok", "fallback", "local")
    assert data["results"]["午餐"]["dishes"]


def test_llm_test_endpoint_explains_local_mode(client):
    resp = client.post("/api/test/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "本地菜谱库" in data["message"]


def test_plan_edit_saves_steps(client):
    """手动编辑一餐时，做法步骤要能存下来并在「简单做法」页显示。"""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Plan

    target = "2024-07-14"
    client.post("/api/generate", json={"target_date": target, "meals": ["午餐"], "force": True})

    db = SessionLocal()
    plan = db.execute(
        select(Plan).where(Plan.plan_date == date(2024, 7, 14), Plan.meal == "午餐")
    ).scalar_one()
    first_name = plan.dishes[0]["name"]
    # 注意：httpx 的 data 要用「值是列表的字典」才能编码成重复字段，
    # 传 list[tuple] 会被当成 raw body，表单全空 —— 这个坑踩过一次。
    form: dict[str, list[str] | str] = {
        "soup": plan.soup,
        "staple": plan.staple,
        "reason": "手工测试",
        "dish_name": [d["name"] for d in plan.dishes],
        "dish_category": [d["category"] for d in plan.dishes],
        "dish_ingredients": ["，".join(d.get("ingredients") or []) for d in plan.dishes],
        "dish_note": [d.get("note") or "" for d in plan.dishes],
        "dish_steps": ["①手工改的步骤A ②手工改的步骤B ③出锅" for _ in plan.dishes],
    }
    db.close()

    resp = client.post(f"/plans/{target}/午餐/edit", data=form, follow_redirects=False)
    assert resp.status_code == 303

    recipes = client.get(f"/plans/{target}/recipes")
    assert recipes.status_code == 200
    assert "手工改的步骤A" in recipes.text  # steps 落库并渲染

    detail = client.get(f"/plans/{target}")
    assert detail.status_code == 200
    assert first_name in detail.text


def test_recipes_page_without_plan(client):
    resp = client.get("/plans/1999-01-01/recipes")
    assert resp.status_code == 200
    assert "还没有菜单" in resp.text


def test_shopping_page(client):
    assert client.get("/plans/2024-07-11/shopping").status_code == 200


def test_logs_page(client):
    resp = client.get("/logs")
    assert resp.status_code == 200
    assert "推送记录" in resp.text
