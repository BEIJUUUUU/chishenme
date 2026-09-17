"""Web 层冒烟测试：登录、页面渲染、JSON 接口。"""
from __future__ import annotations

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


def test_root_redirects_to_login_when_anonymous(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "登录" in resp.text


def test_dashboard_after_login(auth_client):
    resp = auth_client.get("/dashboard")
    assert resp.status_code == 200
    assert "今天吃什么" in resp.text


def test_settings_page_renders(auth_client):
    resp = auth_client.get("/settings")
    assert resp.status_code == 200
    assert "家庭画像" in resp.text
    assert "企业微信机器人" in resp.text


def test_settings_save_roundtrip(auth_client):
    resp = auth_client.post(
        "/settings",
        data={
            "family_name": "老王家",
            "province": "四川",
            "city": "成都",
            "people": "5",
            "lunch_count": "4",
            "dinner_count": "4",
            "staple": "米饭",
            "spicy": "1",
            "budget": "80",
            "llm_mode": "openai",
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

    page = auth_client.get("/settings")
    assert "老王家" in page.text
    assert 'value="四川" selected' in page.text or "四川" in page.text


def test_dishes_page_and_seed(auth_client):
    auth_client.post("/dishes/seed", follow_redirects=False)
    resp = auth_client.get("/dishes")
    assert resp.status_code == 200
    assert "菜谱库" in resp.text


def test_api_plans_requires_auth(client):
    resp = client.get("/api/plans/2024-07-10")
    assert resp.status_code == 401


def test_api_plans_after_login(auth_client):
    resp = auth_client.get("/api/plans/2024-07-10")
    assert resp.status_code == 200
    assert resp.json()["date"] == "2024-07-10"


def test_generate_api_without_llm_key_falls_back(auth_client):
    """没配 API Key 时不应 500，而是走本地兜底。"""
    resp = auth_client.post(
        "/api/generate",
        json={"target_date": "2024-07-11", "meals": ["午餐"], "force": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["results"]["午餐"]["status"] in ("ok", "fallback")


def test_shopping_page(auth_client):
    resp = auth_client.get("/plans/2024-07-11/shopping")
    assert resp.status_code == 200


def test_logs_page(auth_client):
    resp = auth_client.get("/logs")
    assert resp.status_code == 200
    assert "推送记录" in resp.text
