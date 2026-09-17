"""本地菜谱库管理。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ..core.pantry import MEAT, province_tags, seed_database
from ..deps import AppConfigDep, CurrentUser, DbSession
from ..models import Dish, Plan
from ..runtime_config import CATEGORIES, PROVINCES
from ..web import render

router = APIRouter(tags=["dishes"])


def _tags(raw: str) -> list[str]:
    return [p.strip() for p in str(raw).replace("，", ",").replace("、", ",").split(",") if p.strip()]


@router.get("/dishes")
def dishes_page(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
    q: str = "",
    province: str = "",
    category: str = "",
    source: str = "",
    page: int = 1,
):
    page = max(1, page)
    per_page = 40
    stmt = select(Dish)
    rows = db.execute(stmt.order_by(Dish.province, Dish.category, Dish.name)).scalars().all()

    keyword = q.strip()
    filtered = []
    for dish in rows:
        if keyword and keyword not in dish.name and not any(keyword in i for i in (dish.ingredients or [])):
            continue
        if province and dish.province != province:
            continue
        if category and dish.category != category:
            continue
        if source and dish.source != source:
            continue
        filtered.append(dish)

    total = len(filtered)
    start = (page - 1) * per_page
    items = filtered[start : start + per_page]
    pages = max(1, (total + per_page - 1) // per_page)

    provinces = sorted({d.province for d in rows})
    return render(
        request,
        "dishes.html",
        user=user,
        config=config,
        dishes=items,
        total=total,
        page=page,
        pages=pages,
        q=q,
        province=province,
        category=category,
        source=source,
        provinces=provinces,
        categories=CATEGORIES,
        allow_provinces=PROVINCES,
        my_province_tags=province_tags(config.province),
    )


@router.post("/dishes/new")
def dish_new(
    db: DbSession,
    user: CurrentUser,
    name: str = Form(""),
    province: str = Form("通用"),
    category: str = Form(MEAT),
    season: str = Form("四季"),
    ingredients: str = Form(""),
    tags: str = Form(""),
    spicy: int = Form(0),
    howto: str = Form(""),
    steps: str = Form(""),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/dishes?msg=菜名不能为空&level=error", status_code=303)
    exists = db.execute(select(Dish).where(Dish.name == name)).scalar_one_or_none()
    if exists:
        return RedirectResponse("/dishes?msg=这道菜已存在&level=warn", status_code=303)
    db.add(
        Dish(
            name=name,
            province=province or "通用",
            category=category or MEAT,
            season=season or "四季",
            ingredients=_tags(ingredients),
            tags=_tags(tags),
            spicy=max(0, min(3, spicy)),
            howto=howto.strip()[:60],
            steps=steps.strip()[:220],
            source="manual",
        )
    )
    db.commit()
    return RedirectResponse("/dishes?msg=已添加 ✅&level=ok", status_code=303)


@router.post("/dishes/{dish_id}/edit")
def dish_edit(
    dish_id: int,
    db: DbSession,
    user: CurrentUser,
    name: str = Form(""),
    province: str = Form("通用"),
    category: str = Form(MEAT),
    season: str = Form("四季"),
    ingredients: str = Form(""),
    tags: str = Form(""),
    spicy: int = Form(0),
    howto: str = Form(""),
    steps: str = Form(""),
    enabled: str = Form(""),
):
    dish = db.get(Dish, dish_id)
    if dish is None:
        return RedirectResponse("/dishes?msg=菜品不存在&level=error", status_code=303)
    if name.strip():
        dish.name = name.strip()[:64]
    dish.province = province or "通用"
    dish.category = category or MEAT
    dish.season = season or "四季"
    dish.ingredients = _tags(ingredients)
    dish.tags = _tags(tags)
    dish.spicy = max(0, min(3, spicy))
    dish.howto = howto.strip()[:60]
    dish.steps = steps.strip()[:220]
    dish.enabled = bool(enabled)
    db.commit()
    return RedirectResponse("/dishes?msg=已更新 ✅&level=ok", status_code=303)


@router.post("/dishes/{dish_id}/toggle")
def dish_toggle(dish_id: int, db: DbSession, user: CurrentUser):
    dish = db.get(Dish, dish_id)
    if dish is None:
        return RedirectResponse("/dishes?msg=菜品不存在&level=error", status_code=303)
    dish.enabled = not dish.enabled
    db.commit()
    state = "启用" if dish.enabled else "停用"
    return RedirectResponse(f"/dishes?msg={dish.name} 已{state}&level=ok", status_code=303)


@router.post("/dishes/{dish_id}/delete")
def dish_delete(dish_id: int, db: DbSession, user: CurrentUser):
    dish = db.get(Dish, dish_id)
    if dish is None:
        return RedirectResponse("/dishes?msg=菜品不存在&level=error", status_code=303)
    name = dish.name
    db.delete(dish)
    db.commit()
    return RedirectResponse(f"/dishes?msg=已删除 {name}&level=ok", status_code=303)


@router.post("/dishes/seed")
def dish_seed(db: DbSession, user: CurrentUser):
    added = seed_database(db, force=False)
    return RedirectResponse(f"/dishes?msg=已导入内置菜谱 {added} 道&level=ok", status_code=303)


@router.post("/dishes/harvest")
def dish_harvest(
    db: DbSession,
    user: CurrentUser,
    target_date: date = Form(...),
    meal: str = Form("午餐"),
):
    """把某餐里手动加的好菜收进本地库，下次可被复用。"""
    plan = db.execute(
        select(Plan).where(Plan.plan_date == target_date, Plan.meal == meal)
    ).scalar_one_or_none()
    if plan is None:
        return RedirectResponse(f"/plans/{target_date}?msg=该餐不存在&level=error", status_code=303)

    existing = {d.name for d in db.execute(select(Dish)).scalars().all()}
    recipes = plan.recipes or {}
    added = 0
    for dish in plan.dishes or []:
        name = str(dish.get("name", "")).strip()
        if not name or name in existing:
            continue
        recipe = recipes.get(name) or {}
        db.add(
            Dish(
                name=name[:64],
                province="通用",
                category=str(dish.get("category", MEAT)) or MEAT,
                season="四季",
                ingredients=list(dish.get("ingredients") or []),
                tags=["手动收录"],
                spicy=int(dish.get("spicy", 0) or 0),
                howto=str(recipe.get("howto") or dish.get("note") or "").strip()[:60],
                steps=str(recipe.get("steps") or dish.get("steps") or "").strip()[:220],
                source="manual",
            )
        )
        existing.add(name)
        added += 1
    db.commit()
    return RedirectResponse(
        f"/plans/{target_date}?msg=已收录 {added} 道菜到本地库&level=ok", status_code=303
    )
