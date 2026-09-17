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


templates.env.filters["pretty_date"] = _pretty_date
templates.env.globals.update(
    app_name=get_settings().app_name,
    version=VERSION,
    season_label=season_label,
    season_tip=season_tip,
)


def render(request: Request, template: str, **context: Any) -> HTMLResponse:
    context.setdefault("config", None)
    context.setdefault("user", None)
    context.setdefault("msg", request.query_params.get("msg", ""))
    context.setdefault("level", request.query_params.get("level", "ok"))
    return templates.TemplateResponse(request, template, context)


def nav_context(config: AppConfig | None) -> dict:
    return {"settings_schema": SETTINGS_SCHEMA, "nav_config": config}
