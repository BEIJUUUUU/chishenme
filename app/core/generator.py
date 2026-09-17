"""生成编排：LLM 生成 → 本地校验 → 定点重试 → 本地库兜底 → 入库。

对外主入口：
    await generate_day(db, cfg, date, meals=("午餐", "晚餐"))
"""
from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import LLMError, LLMResult, build_llm, is_configured
from ..llm.json_utils import coerce_str_list, extract_json
from ..models import GenerationLog, Plan
from ..runtime_config import AppConfig
from . import pantry, prompt, shopping

VALID_CATEGORIES = {"荤菜", "素菜", "凉菜", "汤"}


# ---------------------------------------------------------------------------
# 规范化 LLM 返回
# ---------------------------------------------------------------------------
def _normalize_dish(raw) -> dict | None:
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            return None
        return {"name": name, "category": "荤菜", "ingredients": [], "spicy": 0, "note": "", "steps": ""}

    if not isinstance(raw, dict):
        return None

    name = str(raw.get("name") or raw.get("dish") or raw.get("菜名") or "").strip()
    if not name:
        return None

    category = str(raw.get("category") or raw.get("type") or "荤菜").strip()
    if category not in VALID_CATEGORIES:
        for candidate in VALID_CATEGORIES:
            if candidate in category:
                category = candidate
                break
        else:
            category = "荤菜"

    try:
        spicy = int(raw.get("spicy", 0) or 0)
    except (TypeError, ValueError):
        spicy = 0
    spicy = max(0, min(3, spicy))

    ingredients = coerce_str_list(raw.get("ingredients") or raw.get("食材"))
    note = str(raw.get("note") or raw.get("做法要点") or raw.get("做法") or "").strip()[:60]
    steps = str(raw.get("steps") or raw.get("步骤") or "").strip()[:220]
    if not steps:
        raw_steps = raw.get("steps")
        if isinstance(raw_steps, list):
            steps = " ".join(
                f"{'①②③④⑤'[i]}{str(s).strip()}" for i, s in enumerate(raw_steps[:4]) if str(s).strip()
            )[:220]

    return {
        "name": name[:40],
        "category": category,
        "ingredients": [i[:20] for i in ingredients][:8],
        "spicy": spicy,
        "note": note,
        "steps": steps,
    }


def _normalize_meals(data: dict, wanted: list[str]) -> dict[str, dict]:
    raw_meals = data.get("meals")
    if raw_meals is None:
        raw_meals = data.get("menu") or data.get("plan") or []
    if isinstance(raw_meals, dict):
        raw_meals = [{"meal": k, **v} if isinstance(v, dict) else {"meal": k, "dishes": v} for k, v in raw_meals.items()]
    if not isinstance(raw_meals, list):
        raw_meals = [data]

    # 单餐且没写 meal 字段的情况
    if len(raw_meals) == 1 and isinstance(raw_meals[0], dict) and not raw_meals[0].get("meal"):
        raw_meals[0] = {**raw_meals[0], "meal": wanted[0] if wanted else "午餐"}

    out: dict[str, dict] = {}
    for item in raw_meals:
        if not isinstance(item, dict):
            continue
        meal_name = str(item.get("meal") or item.get("餐") or "").strip()
        matched = next((w for w in wanted if w in meal_name or meal_name in w), None)
        if matched is None:
            continue
        dishes = [d for d in (_normalize_dish(x) for x in (item.get("dishes") or item.get("菜品") or [])) if d]
        soup = str(item.get("soup") or item.get("汤") or "").strip()[:40]
        if soup and soup in {"无", "无汤", "none", "None", "null"}:
            soup = ""
        out[matched] = {
            "dishes": dishes,
            "soup": soup,
            "staple": str(item.get("staple") or item.get("主食") or "").strip()[:20],
            "reason": str(item.get("reason") or item.get("搭配思路") or "").strip()[:200],
        }
    return out


def _expected_count(cfg: AppConfig, meal: str) -> int:
    return cfg.lunch_count if meal == "午餐" else cfg.dinner_count


# ---------------------------------------------------------------------------
# 单餐生成
# ---------------------------------------------------------------------------
async def _generate_one_meal(
    db: Session,
    cfg: AppConfig,
    *,
    target: date,
    meal: str,
    recent: set[str],
    llm,
) -> tuple[dict, list[dict], int, str]:
    """返回 (meal_data, issues, attempts, provider_model)。"""
    wanted = [meal]
    count = _expected_count(cfg, meal)
    counts = {meal: count}

    messages = prompt.build_menu_messages(
        cfg, target=target, meals=wanted, recent=recent, counts=counts
    )

    last_data: dict = {}
    last_issues: list[dict] = []
    last_text = ""
    attempts = 0

    for round_index in range(max(1, cfg.llm_max_repair + 1)):
        attempts = round_index + 1
        started = time.perf_counter()
        try:
            result: LLMResult = await llm.chat(messages, json_mode=True)
        except LLMError as exc:
            db.add(
                GenerationLog(
                    target_date=target,
                    meal=meal,
                    provider=getattr(llm, "provider", ""),
                    model=getattr(llm, "model", ""),
                    ok=False,
                    attempts=attempts,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    error=str(exc)[:400],
                )
            )
            db.commit()
            if round_index >= cfg.llm_max_repair:
                raise
            await asyncio.sleep(1.5 * (round_index + 1))
            continue

        last_text = result.text
        try:
            data = extract_json(result.text)
        except ValueError as exc:
            last_issues = [{"level": "error", "code": "json", "message": f"返回不是合法 JSON：{exc}"}]
            db.add(
                GenerationLog(
                    target_date=target, meal=meal, provider=result.provider, model=result.model,
                    ok=False, attempts=attempts, elapsed_ms=result.elapsed_ms,
                    prompt_tokens=result.prompt_tokens, error="JSON 解析失败",
                )
            )
            db.commit()
        else:
            normalized = _normalize_meals(data, wanted)
            last_data = normalized.get(meal, last_data)
            if not last_data:
                last_issues = [{"level": "error", "code": "missing", "message": f"返回里没有「{meal}」的内容"}]
            else:
                issues = pantry.validate_meal(
                    cfg,
                    last_data.get("dishes", []),
                    target=target,
                    recent=recent,
                    expected_count=count,
                    soup=last_data.get("soup", ""),
                )
                errors = pantry.errors_of(issues)
                db.add(
                    GenerationLog(
                        target_date=target, meal=meal, provider=result.provider, model=result.model,
                        ok=not errors, attempts=attempts, elapsed_ms=result.elapsed_ms,
                        prompt_tokens=result.prompt_tokens,
                        error="; ".join(pantry.issue_text(errors))[:400],
                    )
                )
                db.commit()
                if not errors:
                    return last_data, issues, attempts, f"{result.provider}:{result.model}"
                last_issues = issues

        if round_index < cfg.llm_max_repair:
            messages = prompt.build_repair_messages(
                cfg, target=target, previous=last_text, issues=last_issues,
                meals=wanted, counts=counts, recent=recent,
            )

    raise GenerationFailure(pantry.issue_text(last_issues) or ["生成失败"], attempts)


class GenerationFailure(RuntimeError):
    def __init__(self, reasons: list[str], attempts: int = 1) -> None:
        super().__init__("；".join(reasons))
        self.reasons = reasons
        self.attempts = attempts


# ---------------------------------------------------------------------------
# 一天两餐
# ---------------------------------------------------------------------------
def lookup_recipe(db: Session, name: str) -> dict:
    """菜名 → {howto, steps, ingredients}。

    汤在菜单里只有名字，靠这里从本地库补回做法与食材；
    LLM 生成的菜如果本地库里有，也能顺手补上更权威的做法。
    """
    from ..models import Dish

    text = (name or "").strip()
    if not text:
        return {}
    dish = db.execute(select(Dish).where(Dish.name == text)).scalar_one_or_none()
    if dish is None:
        return {}
    return {
        "howto": dish.howto or "",
        "steps": dish.steps or "",
        "ingredients": list(dish.ingredients or []),
    }


def resolve_soup_ingredients(db: Session, soup: str) -> list[str]:
    """汤名 → 食材。本地库里有这道汤就用它的食材，没有就返回空（宁缺勿错）。"""
    return list(lookup_recipe(db, soup).get("ingredients") or [])


def _build_recipes(db: Session, meal_data: dict) -> dict:
    """把这一餐的做法固化成快照：{菜名: {howto, steps}}。

    菜单生成后菜谱库还可能被改，快照保证「当时是怎么做的」随时查得到。
    """
    recipes: dict[str, dict] = {}
    for dish in meal_data.get("dishes") or []:
        name = str(dish.get("name") or "").strip()
        if not name:
            continue
        lib = lookup_recipe(db, name)
        recipes[name] = {
            "howto": str(dish.get("note") or "").strip() or lib.get("howto", ""),
            "steps": str(dish.get("steps") or "").strip() or lib.get("steps", ""),
        }

    soup = str(meal_data.get("soup") or "").strip()
    if soup:
        lib = lookup_recipe(db, soup)
        recipes[soup] = {"howto": lib.get("howto", ""), "steps": lib.get("steps", "")}
    return recipes


def _apply_shopping(db: Session, meal_data: dict, cfg: AppConfig) -> list[dict]:
    """把一餐的食材汇总成购物清单。

    汤只在本地库能查到食材时才参与汇总 —— 绝不要把「番茄鸡蛋汤」这种菜名
    当食材丢进分类器，否则会跑出「肉蛋类：番茄鸡蛋汤」这种荒唐结果。
    """
    items: list[dict] = list(meal_data.get("dishes", []))
    soup_ingredients = resolve_soup_ingredients(db, meal_data.get("soup", ""))
    if soup_ingredients:
        items.append({"name": meal_data.get("soup", ""), "ingredients": soup_ingredients})
    return shopping.aggregate(items)


def upsert_plan(db: Session, cfg: AppConfig, target: date, meal: str, meal_data: dict, *, source: str, status: str = "ok", issues: list[dict] | None = None, model: str = "") -> Plan:
    plan = db.execute(
        select(Plan).where(Plan.plan_date == target, Plan.meal == meal)
    ).scalar_one_or_none()
    if plan is None:
        plan = Plan(plan_date=target, meal=meal)
        db.add(plan)

    plan.dishes = list(meal_data.get("dishes", []))
    plan.soup = meal_data.get("soup", "") or ""
    plan.staple = meal_data.get("staple", "") or cfg.staple
    plan.reason = meal_data.get("reason", "") or ""
    plan.shopping = _apply_shopping(db, meal_data, cfg)
    plan.recipes = _build_recipes(db, meal_data)
    plan.status = status
    plan.source = source
    plan.issues = [i.get("message", "") for i in (issues or [])]
    plan.model = model
    plan.pushed_at = None
    db.commit()
    db.refresh(plan)
    return plan


def _recent_for(db: Session, cfg: AppConfig, target: date, meal: str, plan_id: int | None) -> set[str]:
    """最近 N 天（含当天）吃过的菜，用于查重。

    只排除「正在被替换的那一餐」本身（按 id），同一天的另一餐必须保留在集合里 ——
    否则中午和晚上会排出一模一样的菜单。
    """
    start = target - timedelta(days=cfg.repeat_window_days)
    rows = db.execute(select(Plan).where(Plan.plan_date >= start, Plan.plan_date <= target)).scalars().all()
    names: set[str] = set()
    for row in rows:
        if plan_id is not None and row.id == plan_id:
            continue
        names.update(row.all_dish_names)
    return names


async def generate_day(
    db: Session,
    cfg: AppConfig,
    target: date | None = None,
    *,
    meals: tuple[str, ...] = ("午餐", "晚餐"),
    force: bool = False,
) -> dict[str, Plan]:
    """生成（或重新生成）某天的菜单。返回 {餐次: Plan}。

    没配置大模型（通道为「仅本地菜谱库」或没填 Key）时，直接用本地库搭配，
    不重试、不等待、不写错误日志 —— 保证「打开即用」。
    """
    target = target or date.today()
    results: dict[str, Plan] = {}

    existing = {
        p.meal: p
        for p in db.execute(select(Plan).where(Plan.plan_date == target)).scalars().all()
    }

    if not is_configured(cfg):
        for meal in meals:
            current = existing.get(meal)
            recent = _recent_for(db, cfg, target, meal, current.id if current else None)
            fallback = pantry.compose_fallback(
                db, cfg, target=target, count=_expected_count(cfg, meal), recent=recent
            )
            results[meal] = upsert_plan(
                db, cfg, target, meal, fallback,
                source="local",
                status="local" if fallback.get("dishes") else "failed",
                model="local-library",
            )
        return results

    llm = build_llm(cfg)
    try:
        for meal in meals:
            if not force and meal in existing and existing[meal].dishes:
                results[meal] = existing[meal]
                continue

            current = existing.get(meal)
            recent = _recent_for(db, cfg, target, meal, current.id if current else None)

            try:
                meal_data, issues, _attempts, model = await _generate_one_meal(
                    db, cfg, target=target, meal=meal, recent=recent, llm=llm
                )
                plan = upsert_plan(db, cfg, target, meal, meal_data, source="llm", status="ok", issues=issues, model=model)
            except (GenerationFailure, LLMError) as exc:
                reasons = getattr(exc, "reasons", [str(exc)])
                fallback = pantry.compose_fallback(
                    db, cfg, target=target, count=_expected_count(cfg, meal), recent=recent
                )
                plan = upsert_plan(
                    db, cfg, target, meal, fallback,
                    source="local",
                    status=fallback.get("status", "fallback"),
                    issues=[{"message": r} for r in reasons],
                    model="local-library",
                )
            results[meal] = plan
    finally:
        await llm.aclose()

    return results


async def regenerate_meal(
    db: Session,
    cfg: AppConfig,
    target: date,
    meal: str,
    *,
    mode: str = "llm",
) -> Plan:
    """单餐重新生成。

    mode='local' 强制本地库；mode='llm' 走大模型 —— 但没配置大模型时会自动退回本地库。
    """
    if mode == "local" or not is_configured(cfg):
        recent = _recent_for(db, cfg, target, meal, None)
        fallback = pantry.compose_fallback(
            db, cfg, target=target, count=_expected_count(cfg, meal), recent=recent
        )
        status = "fallback" if mode == "local" else "local"
        return upsert_plan(db, cfg, target, meal, fallback, source="local", status=status)

    result = await generate_day(db, cfg, target, meals=(meal,), force=True)
    return result[meal]
