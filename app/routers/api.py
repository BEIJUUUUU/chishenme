"""JSON 接口：给前端异步按钮和外部自动化调用。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import select

from ..config import get_settings
from ..core.generator import generate_day
from ..core.message import day_markdown, day_plain, shopping_list_text
from ..deps import AppConfigDep, CurrentUserApi, DbSession
from ..llm import list_models, test_connection
from ..models import Plan
from ..services import load_plans, push_day, send_test_message
from ..version import VERSION

router = APIRouter(tags=["api"])


@router.get("/healthz")
def healthz():
    return {"status": "ok", "app": get_settings().app_name, "version": VERSION}


@router.get("/api/plans/{target_date}")
def api_plans(target_date: date, db: DbSession, user: CurrentUserApi):
    plans = load_plans(db, target_date)
    return {
        "date": target_date.isoformat(),
        "meals": [
            {
                "meal": plan.meal,
                "dishes": plan.dishes,
                "soup": plan.soup,
                "staple": plan.staple,
                "reason": plan.reason,
                "status": plan.status,
                "source": plan.source,
                "issues": plan.issues,
            }
            for plan in plans
        ],
        "shopping": shopping_list_text(plans),
    }


@router.get("/api/plans/{target_date}/markdown")
def api_markdown(target_date: date, db: DbSession, user: CurrentUserApi, config: AppConfigDep):
    plans = load_plans(db, target_date)
    if not plans:
        raise HTTPException(status_code=404, detail="该日期没有菜单")
    title = f"{config.push_title_prefix} · {target_date.isoformat()}"
    return {
        "markdown": day_markdown(plans, title=title, family=config.family_name),
        "plain": day_plain(plans, title=title, family=config.family_name),
    }


@router.post("/api/generate")
async def api_generate(
    db: DbSession,
    user: CurrentUserApi,
    config: AppConfigDep,
    target_date: str = Body("", embed=True),
    meals: list[str] = Body(default=["午餐", "晚餐"], embed=True),
    force: bool = Body(True, embed=True),
):
    try:
        target = date.fromisoformat(target_date) if target_date else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from exc

    wanted = tuple(m for m in meals if m in ("午餐", "晚餐")) or ("午餐", "晚餐")
    plans = await generate_day(db, config, target, meals=wanted, force=force)
    return {
        "ok": True,
        "date": target.isoformat(),
        "results": {meal: {"status": plan.status, "source": plan.source, "dishes": plan.dish_names} for meal, plan in plans.items()},
    }


@router.post("/api/push")
async def api_push(
    db: DbSession,
    user: CurrentUserApi,
    config: AppConfigDep,
    target_date: str = Body("", embed=True),
    channels: list[str] = Body(default=[], embed=True),
):
    try:
        target = date.fromisoformat(target_date) if target_date else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from exc
    results = await push_day(db, config, target, channels=channels or None)
    return {"ok": any(r["ok"] for r in results), "results": results}


@router.post("/api/test/llm")
async def api_test_llm(config: AppConfigDep, user: CurrentUserApi):
    ok, message, model = await test_connection(config)
    return {"ok": ok, "message": message, "model": model, "provider": config.llm_mode}


@router.post("/api/llm/models")
async def api_llm_models(config: AppConfigDep, user: CurrentUserApi):
    """拉取当前通道的模型列表，供设置页一键填入。

    对「手填模型名」很痛苦的反代/网关特别有用：cliproxy、one-api 之类
    返回的模型别名往往和官方文档不一样。
    """
    ok, message, models = await list_models(config)
    return {"ok": ok, "message": message, "models": models, "provider": config.llm_mode}


@router.post("/api/test/push/{channel}")
async def api_test_push(channel: str, db: DbSession, user: CurrentUserApi, config: AppConfigDep):
    result = await send_test_message(db, config, channel)
    return result


@router.get("/api/stats")
def api_stats(db: DbSession, user: CurrentUserApi):
    plans = db.execute(select(Plan)).scalars().all()
    return {
        "plans": len(plans),
        "generated": sum(1 for p in plans if p.source == "llm"),
        "fallback": sum(1 for p in plans if p.source != "llm"),
    }
