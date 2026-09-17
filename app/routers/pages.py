"""页面路由：仪表盘、菜单列表、菜单详情/编辑、购物清单、日志。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ..core import shopping
from ..core.generator import generate_day, regenerate_meal
from ..core.message import date_label, shopping_list_text
from ..deps import AppConfigDep, CurrentUser, DbSession
from ..models import Dish, GenerationLog, Plan, PushLog
from ..scheduler import scheduler
from ..services import push_day
from ..web import render

router = APIRouter(tags=["pages"])

WEEKDAYS = "一二三四五六日"


def _redirect(url: str, msg: str = "", level: str = "ok") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    if msg:
        url = f"{url}{sep}msg={msg}&level={level}"
    return RedirectResponse(url, status_code=303)


@router.get("/")
def index(user: CurrentUser):
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, db: DbSession, user: CurrentUser, config: AppConfigDep):
    today = date.today()
    tomorrow = today + timedelta(days=1)

    def plans_of(target: date) -> list[Plan]:
        rows = db.execute(select(Plan).where(Plan.plan_date == target)).scalars().all()
        order = {"午餐": 0, "晚餐": 1}
        return sorted(rows, key=lambda p: order.get(p.meal, 9))

    today_plans = plans_of(today)
    tomorrow_plans = plans_of(tomorrow)
    today_shopping = shopping.merge_plans(today_plans)
    recent_push = (
        db.execute(select(PushLog).order_by(PushLog.id.desc()).limit(8)).scalars().all()
    )
    stats = {
        "dishes": len(db.execute(select(Dish)).scalars().all()),
        "plans": len(db.execute(select(Plan)).scalars().all()),
    }

    return render(
        request,
        "dashboard.html",
        user=user,
        config=config,
        today=today,
        tomorrow=tomorrow,
        today_plans=today_plans,
        tomorrow_plans=tomorrow_plans,
        today_shopping=today_shopping,
        recent_push=recent_push,
        stats=stats,
        jobs=scheduler.jobs(),
        weekday=WEEKDAYS[today.weekday()],
    )


@router.get("/plans")
def plans_page(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
    days: int = 14,
):
    days = max(3, min(60, days))
    start = date.today() - timedelta(days=3)
    end = date.today() + timedelta(days=days)
    rows = (
        db.execute(select(Plan).where(Plan.plan_date >= start, Plan.plan_date <= end))
        .scalars()
        .all()
    )
    grouped: dict[date, dict[str, Plan]] = {}
    for plan in rows:
        grouped.setdefault(plan.plan_date, {})[plan.meal] = plan

    timeline = []
    cursor = start
    while cursor <= end:
        timeline.append(
            {
                "date": cursor,
                "weekday": WEEKDAYS[cursor.weekday()],
                "is_today": cursor == date.today(),
                "meals": grouped.get(cursor, {}),
            }
        )
        cursor += timedelta(days=1)
    timeline.reverse()

    return render(request, "plans.html", user=user, config=config, timeline=timeline, days=days)


@router.get("/plans/{target_date}")
def plan_detail(
    request: Request,
    target_date: date,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
):
    rows = (
        db.execute(select(Plan).where(Plan.plan_date == target_date)).scalars().all()
    )
    order = {"午餐": 0, "晚餐": 1}
    plans = sorted(rows, key=lambda p: order.get(p.meal, 9))
    logs = (
        db.execute(
            select(PushLog).where(PushLog.plan_id.in_([p.id for p in plans] or [0])).order_by(PushLog.id.desc()).limit(10)
        )
        .scalars()
        .all()
        if plans
        else []
    )
    return render(
        request,
        "plan_detail.html",
        user=user,
        config=config,
        target=target_date,
        plans=plans,
        logs=logs,
        weekday=WEEKDAYS[target_date.weekday()],
        is_today=target_date == date.today(),
    )


@router.post("/plans/{target_date}/generate")
async def plan_generate(
    target_date: date,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
    force: str = Form(""),
):
    try:
        plans = await generate_day(db, config, target_date, force=bool(force))
        failed = [p.meal for p in plans.values() if p.status == "failed"]
        if failed:
            return _redirect(f"/plans/{target_date}", f"生成完成，但 {'、'.join(failed)} 失败", "warn")
        fallback = [p.meal for p in plans.values() if p.status == "fallback"]
        if fallback:
            return _redirect(
                f"/plans/{target_date}",
                f"生成完成（{'、'.join(fallback)} 用了本地菜库兜底，可点重新生成重试）",
                "warn",
            )
        return _redirect(f"/plans/{target_date}", "菜单生成完成 ✅")
    except Exception as exc:
        return _redirect(f"/plans/{target_date}", f"生成失败：{exc}", "error")


@router.post("/plans/{target_date}/{meal}/regenerate")
async def plan_regenerate(
    target_date: date,
    meal: str,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
    mode: str = Form("llm"),
):
    try:
        plan = await regenerate_meal(db, config, target_date, meal, mode=mode)
        if plan.status == "failed":
            return _redirect(f"/plans/{target_date}", f"{meal} 重生成失败", "error")
        if plan.status == "fallback":
            return _redirect(f"/plans/{target_date}", f"{meal} 已用本地菜库重新搭配", "warn")
        return _redirect(f"/plans/{target_date}", f"{meal} 已重新生成 ✅")
    except Exception as exc:
        return _redirect(f"/plans/{target_date}", f"重生成失败：{exc}", "error")


@router.post("/plans/{target_date}/{meal}/edit")
async def plan_edit(
    target_date: date,
    meal: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
):
    plan = db.execute(
        select(Plan).where(Plan.plan_date == target_date, Plan.meal == meal)
    ).scalar_one_or_none()
    if plan is None:
        return _redirect(f"/plans/{target_date}", "该餐还没有菜单", "error")

    form = await request.form()
    names = list(form.getlist("dish_name"))
    categories = list(form.getlist("dish_category"))
    ingredients = list(form.getlist("dish_ingredients"))
    notes = list(form.getlist("dish_note"))
    deleted = set(form.getlist("dish_delete"))

    dishes: list[dict] = []
    for index, name in enumerate(names):
        if str(index) in deleted:
            continue
        name = name.strip()
        if not name:
            continue
        raw_ings = ingredients[index] if index < len(ingredients) else ""
        ings = [
            part.strip()
            for part in str(raw_ings).replace("，", ",").replace("、", ",").replace(" ", ",").split(",")
            if part.strip()
        ]
        dishes.append(
            {
                "name": name[:40],
                "category": (categories[index] if index < len(categories) else "荤菜") or "荤菜",
                "ingredients": ings[:10],
                "note": (notes[index] if index < len(notes) else "").strip()[:60],
                "spicy": 0,
            }
        )

    new_names = [n.strip() for n in form.getlist("new_dish_name") if n.strip()]
    new_cats = list(form.getlist("new_dish_category"))
    new_ings = list(form.getlist("new_dish_ingredients"))
    for index, name in enumerate(new_names):
        raw = new_ings[index] if index < len(new_ings) else ""
        ings = [p.strip() for p in str(raw).replace("，", ",").replace("、", ",").split(",") if p.strip()]
        dishes.append(
            {
                "name": name[:40],
                "category": (new_cats[index] if index < len(new_cats) else "荤菜") or "荤菜",
                "ingredients": ings[:10],
                "note": "",
                "spicy": 0,
            }
        )

    soup = str(form.get("soup") or "").strip()[:40]
    staple = str(form.get("staple") or config.staple).strip()[:20]
    reason = str(form.get("reason") or "").strip()[:200]

    plan.dishes = dishes
    plan.soup = soup
    plan.staple = staple
    plan.reason = reason
    plan.source = "manual"
    plan.shopping = shopping.aggregate(
        dishes, extra=[x for x in (soup, staple) if x]
    )
    plan.updated_at = datetime.now()
    db.commit()

    return _redirect(f"/plans/{target_date}", f"{meal} 已保存 ✅")


@router.post("/plans/{target_date}/push")
async def plan_push(
    target_date: date,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
    with_shopping: str = Form("on"),
):
    plans = db.execute(select(Plan).where(Plan.plan_date == target_date)).scalars().all()
    if not plans:
        return _redirect(f"/plans/{target_date}", "还没有菜单，先点生成", "error")

    results = await push_day(
        db, config, target_date, with_shopping=bool(with_shopping)
    )
    if not results:
        return _redirect(f"/plans/{target_date}", "没有启用任何推送通道，去设置里勾选", "warn")
    ok = [r["channel"] for r in results if r["ok"]]
    bad = [f"{r['channel']}（{r['message']}）" for r in results if not r["ok"]]
    if bad:
        return _redirect(
            f"/plans/{target_date}",
            f"成功：{'、'.join(ok) or '无'}；失败：{'、'.join(bad)}",
            "warn",
        )
    return _redirect(f"/plans/{target_date}", f"已推送到：{'、'.join(ok)} ✅")


@router.get("/plans/{target_date}/shopping")
def shopping_page(request: Request, target_date: date, db: DbSession, user: CurrentUser, config: AppConfigDep):
    plans = (
        db.execute(select(Plan).where(Plan.plan_date == target_date)).scalars().all()
    )
    text = shopping_list_text(plans) if plans else ""
    return render(
        request,
        "shopping.html",
        user=user,
        config=config,
        target=target_date,
        plans=plans,
        shopping_text=text,
        label=date_label(target_date),
    )


@router.get("/logs")
def logs_page(request: Request, db: DbSession, user: CurrentUser, config: AppConfigDep):
    pushes = db.execute(select(PushLog).order_by(PushLog.id.desc()).limit(80)).scalars().all()
    generations = (
        db.execute(select(GenerationLog).order_by(GenerationLog.id.desc()).limit(80)).scalars().all()
    )
    return render(
        request, "logs.html", user=user, config=config, pushes=pushes, generations=generations
    )
