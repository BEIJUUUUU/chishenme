"""pytest 全局配置：在导入 app 之前把数据目录指向仓库内的临时路径。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TMP = _ROOT / ".pytest-runtime"
shutil.rmtree(_TMP, ignore_errors=True)
_TMP.mkdir(parents=True, exist_ok=True)

os.environ["CSM_DATA_DIR"] = str(_TMP)
os.environ["CSM_SECRET_KEY"] = "test-secret-key"
os.environ["CSM_ADMIN_USER"] = "admin"
os.environ["CSM_ADMIN_PASSWORD"] = "test1234"

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def db():
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cfg():
    """默认配置：指向一个假的大模型通道，方便测试里 monkeypatch 掉真实调用。"""
    from app.runtime_config import AppConfig

    return AppConfig(
        family_name="测试家庭",
        province="山东",
        people=4,
        push_channels=[],
        health_flags=[],
        avoid_ingredients=[],
        llm_mode="openai",
        openai_base_url="https://api.example.invalid/v1",
        openai_api_key="test-key",
    )


@pytest.fixture()
def password_mode():
    """临时把访问模式切成「需要登录」，测试结束恢复免登录。"""
    from app.db import SessionLocal
    from app.runtime_config import update_config

    db = SessionLocal()
    update_config(db, {"auth_mode": "password"})
    db.close()
    yield
    db = SessionLocal()
    update_config(db, {"auth_mode": "none"})
    db.close()
