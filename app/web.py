"""Jinja2 环境与渲染辅助。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .core.season import season_label, season_tip
from .runtime_config import SETTINGS_SCHEMA, AppConfig
from .version import VERSION

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _pretty_date(value) -> str:
    try:
        return f"{value.month}月{value.day}日"
    except Exception:
        return str(value)


def plan_badge(plan) -> dict:
    """菜单来源徽章。放这里是为了让三个页面显示同一套口径。"""
    source = getattr(plan, "source", "")
    status = getattr(plan, "status", "")
    if status == "failed":
        return {"text": "生成失败", "cls": "badge-error"}
    if source == "llm":
        return {"text": "AI 生成", "cls": "badge-ok"} if status == "ok" else {"text": "AI 待修", "cls": "badge-warn"}
    if source == "manual":
        return {"text": "手动编辑", "cls": "badge-info"}
    if status == "local":
        return {"text": "本地菜谱库", "cls": "badge-info"}
    if source == "local":
        return {"text": "本地兜底", "cls": "badge-warn"}
    return {"text": status or "未知", "cls": ""}


templates.env.filters["pretty_date"] = _pretty_date
templates.env.globals.update(
    app_name=get_settings().app_name,
    version=VERSION,
    season_label=season_label,
    season_tip=season_tip,
    plan_badge=plan_badge,
)


def render(request: Request, template: str, **context: Any) -> HTMLResponse:
    context.setdefault("config", None)
    context.setdefault("user", None)
    context.setdefault("msg", request.query_params.get("msg", ""))
    context.setdefault("level", request.query_params.get("level", "ok"))
    return templates.TemplateResponse(request, template, context)


def nav_context(config: AppConfig | None) -> dict:
    return {"settings_schema": SETTINGS_SCHEMA, "nav_config": config}
