"""本地菜谱库：种子导入、健康/忌口/重复/搭配校验、兜底拼菜。

定位：LLM 出菜单，本地库做「闸门」和「备胎」。
- 闸门：拦住重复菜、忌口食材、健康风险、辣度超标、荤素失衡。
- 备胎：LLM 连续失败或校验不过时，用本地库拼一桌能吃的。
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Dish, Plan
from ..runtime_config import AppConfig
from .season import dish_matches_season, season_of

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MEAT = "荤菜"
VEG = "素菜"
SOUP = "汤"
COLD = "凉菜"
STAPLE = "主食"

# ---------------------------------------------------------------------------
# 健康规则：flag -> {tag/keyword 命中即触发}
# ---------------------------------------------------------------------------
HEALTH_RULES: dict[str, dict] = {
    "高血压": {
        "level": "error",
        "tags": ["腌制", "卤味", "高盐", "重口"],
        "keywords": ["腊肉", "咸菜", "咸鱼", "腌", "榨菜", "腐乳", "香肠", "火腿肠", "豆瓣酱", "卤"],
        "tip": "高血压：避免腌腊卤味与高盐做法",
    },
    "高血糖": {
        "level": "error",
        "tags": ["甜品", "糖"],
        "keywords": ["冰糖", "白糖", "糖醋", "拔丝", "蜜", "甜品", "银耳莲子羹", "小米粥"],
        "tip": "高血糖：控制糖分与精制碳水",
    },
    "高血脂": {
        "level": "warn",
        "tags": ["油炸", "肥肉", "硬菜"],
        "keywords": ["五花肉", "猪油", "大肠", "肥肠", "油炸", "扣肉", "酥"],
        "tip": "高血脂：少油少肥肉",
    },
    "痛风": {
        "level": "error",
        "tags": ["海鲜", "内脏", "浓汤"],
        "keywords": ["内脏", "猪肝", "腰花", "大肠", "虾", "蟹", "贝", "蛤蜊", "海参", "鲍鱼", "沙丁", "凤尾", "浓汤", "老火"],
        "tip": "痛风：避开高嘌呤（海鲜、内脏、浓肉汤）",
    },
    "胃不好": {
        "level": "warn",
        "tags": ["重辣", "生食", "凉菜"],
        "keywords": ["辣椒", "剁椒", "麻辣", "酸辣", "凉拌", "生"],
        "tip": "胃不好：少辛辣、少生冷",
    },
    "牙口不好": {
        "level": "warn",
        "tags": ["坚果", "硬"],
        "keywords": ["花生", "坚果", "脆骨", "骨", "鱿鱼", "牛筋", "锅巴", "甘蔗"],
        "tip": "牙口不好：优先软烂做法（蒸、炖、羹）",
    },
    "忌辛辣": {
        "level": "error",
        "tags": ["重辣"],
        "keywords": ["辣椒", "花椒", "剁椒", "麻辣", "小米辣"],
        "tip": "忌辛辣",
    },
    "术后恢复": {
        "level": "warn",
        "tags": ["重辣", "油炸", "生食"],
        "keywords": ["辣椒", "油炸", "生"],
        "tip": "术后恢复：清淡易消化",
    },
}


# ---------------------------------------------------------------------------
# 种子库
# ---------------------------------------------------------------------------
def load_seed_dishes() -> list[dict]:
    path = DATA_DIR / "dishes.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_howto() -> dict[str, dict[str, str]]:
    """做法库：菜名 → {howto 一句话要点, steps 三步做法}。

    和 dishes.json 分开维护，是因为「有哪些菜」和「怎么做」变更频率完全不同；
    想给自家菜补做法，只改这个文件即可。
    """
    path = DATA_DIR / "howto.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def seed_database(db: Session, *, force: bool = False) -> int:
    """把内置菜谱导入数据库。返回新增数量。

    附带效果：已经存在的菜如果还没做法，会把做法补上（老库升级用）。
    """
    seeds = load_seed_dishes()
    if not seeds:
        return 0

    howto_table = load_howto()
    existing = {
        dish.name: dish for dish in db.execute(select(Dish)).scalars().all()
    }
    added = 0
    for item in seeds:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        recipe = howto_table.get(name, {})
        howto = str(item.get("howto") or recipe.get("howto") or "").strip()
        steps = str(item.get("steps") or recipe.get("steps") or "").strip()

        if name in existing:
            dish = existing[name]
            # 只补空值，不覆盖用户自己改过的做法
            if not dish.howto and howto:
                dish.howto = howto
            if not dish.steps and steps:
                dish.steps = steps
            continue

        db.add(
            Dish(
                name=name,
                province=item.get("province", "通用"),
                category=item.get("category", MEAT),
                season=item.get("season", "四季"),
                ingredients=list(item.get("ingredients", [])),
                tags=list(item.get("tags", [])),
                spicy=int(item.get("spicy", 0)),
                howto=howto,
                steps=steps,
                source="local",
                enabled=bool(item.get("enabled", True)),
            )
        )
        added += 1
    db.commit()
    return added


# ---------------------------------------------------------------------------
# 最近吃过的菜（用于查重）
# ---------------------------------------------------------------------------
def recent_dish_names(db: Session, target: date, window_days: int, exclude_ids: set[int] | None = None) -> set[str]:
    if window_days <= 0:
        return set()
    start = target - timedelta(days=window_days)
    rows = (
        db.execute(select(Plan).where(Plan.plan_date >= start, Plan.plan_date < target))
        .scalars()
        .all()
    )
    names: set[str] = set()
    for plan in rows:
        if exclude_ids and plan.id in exclude_ids:
            continue
        names.update(plan.all_dish_names)
    return names


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _hit(text_pool: str, tag_pool: list[str], tokens: list[str]) -> str | None:
    for token in tokens:
        if token and token in text_pool:
            return token
    for tag in tag_pool:
        for token in tokens:
            if token and (token in tag or tag in token):
                return token
    return None


def check_health(cfg: AppConfig, dish: dict) -> list[dict]:
    name = str(dish.get("name", ""))
    ingredients = [str(i) for i in (dish.get("ingredients") or [])]
    tags = [str(t) for t in (dish.get("tags") or [])]
    text_pool = " ".join([name, *ingredients, *tags])
    issues: list[dict] = []
    for flag in cfg.health_flags or []:
        rule = HEALTH_RULES.get(flag)
        if not rule:
            continue
        token = _hit(text_pool, tags, rule["keywords"]) or _hit(text_pool, tags, rule["tags"])
        if token:
            issues.append(
                {
                    "level": rule["level"],
                    "code": "health",
                    "dish": name,
                    "message": f"{rule['tip']} ——「{name}」命中「{token}」",
                }
            )
    return issues


def check_avoided(cfg: AppConfig, dish: dict) -> list[dict]:
    name = str(dish.get("name", ""))
    pool = [name, *[str(i) for i in (dish.get("ingredients") or [])]]
    for token in cfg.avoid_ingredients or []:
        token = token.strip()
        if not token:
            continue
        for item in pool:
            if token in item or item in token:
                return [
                    {
                        "level": "error",
                        "code": "avoid",
                        "dish": name,
                        "message": f"「{name}」含忌口食材「{token}」",
                    }
                ]
    return []


def check_spicy(cfg: AppConfig, dish: dict) -> list[dict]:
    try:
        level = int(dish.get("spicy", 0) or 0)
    except (TypeError, ValueError):
        level = 0
    if level > cfg.spicy:
        return [
            {
                "level": "error",
                "code": "spicy",
                "dish": dish.get("name", ""),
                "message": f"「{dish.get('name')}」辣度 {level} 超出家庭上限 {cfg.spicy}",
            }
        ]
    return []


def check_repeat(recent: set[str], dish: dict) -> list[dict]:
    name = str(dish.get("name", ""))
    if name and name in recent:
        return [
            {"level": "error", "code": "repeat", "dish": name, "message": f"「{name}」最近吃过了"}
        ]
    return []


def check_season(cfg: AppConfig, dish: dict, target: date) -> list[dict]:
    if not cfg.strict_season:
        return []
    season = str(dish.get("season", "四季"))
    if not season or dish_matches_season(season, target):
        return []
    return [
        {
            "level": "warn",
            "code": "season",
            "dish": dish.get("name", ""),
            "message": f"「{dish.get('name')}」标注为 {season} 季菜，当前是{season_of(target)}季",
        }
    ]


def validate_meal(
    cfg: AppConfig,
    dishes: list[dict],
    *,
    target: date,
    recent: set[str],
    expected_count: int,
    soup: str = "",
) -> list[dict]:
    """返回问题列表。level='error' 会触发重新生成，'warn' 只提示。"""
    issues: list[dict] = []
    seen: set[str] = set()

    for dish in dishes:
        if not isinstance(dish, dict):
            issues.append({"level": "error", "code": "format", "message": "菜品格式异常"})
            continue
        name = str(dish.get("name", "")).strip()
        if not name:
            issues.append({"level": "error", "code": "format", "message": "出现无名菜品"})
            continue
        if name in seen:
            issues.append({"level": "error", "code": "dup", "dish": name, "message": f"同一餐重复出现「{name}」"})
            continue
        seen.add(name)
        issues.extend(check_repeat(recent, dish))
        issues.extend(check_avoided(cfg, dish))
        issues.extend(check_spicy(cfg, dish))
        issues.extend(check_health(cfg, dish))
        issues.extend(check_season(cfg, dish, target))

    if soup:
        soup_dish = {"name": soup, "category": SOUP, "ingredients": [], "tags": [], "spicy": 0}
        if soup in seen:
            issues.append({"level": "error", "code": "dup", "dish": soup, "message": f"汤「{soup}」与菜品重复"})
        issues.extend(check_repeat(recent, soup_dish))
        issues.extend(check_avoided(cfg, soup_dish))
        issues.extend(check_health(cfg, soup_dish))

    if expected_count and len(dishes) != expected_count:
        issues.append(
            {
                "level": "warn",
                "code": "count",
                "message": f"菜品数为 {len(dishes)}，期望 {expected_count}",
            }
        )

    if cfg.require_meat_and_veg:
        categories = {str(d.get("category", "")) for d in dishes if isinstance(d, dict)}
        has_meat = any(MEAT in c or "荤" in c for c in categories)
        has_veg = any(VEG in c or "素" in c or "凉" in c for c in categories)
        if not has_meat:
            issues.append({"level": "error", "code": "balance", "message": "缺少荤菜，荤素失衡"})
        if not has_veg:
            issues.append({"level": "error", "code": "balance", "message": "缺少素菜，荤素失衡"})

    if cfg.include_soup and not soup:
        issues.append({"level": "warn", "code": "soup", "message": "配置要求配汤但没给汤"})

    return issues


def errors_of(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i.get("level") == "error"]


def warnings_of(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i.get("level") != "error"]


def issue_text(issues: list[dict]) -> list[str]:
    return [str(i.get("message", "")) for i in issues if i.get("message")]


# ---------------------------------------------------------------------------
# 本地库兜底拼菜
# ---------------------------------------------------------------------------
def _dish_dict(dish: Dish) -> dict:
    return {
        "name": dish.name,
        "category": dish.category,
        "ingredients": list(dish.ingredients or []),
        "tags": list(dish.tags or []),
        "spicy": dish.spicy,
        "season": dish.season,
        "howto": dish.howto or "",
        "steps": dish.steps or "",
    }


def province_tags(province: str) -> set[str]:
    """省份 → 允许匹配的菜谱 province 标签（含方言/大区别名）。"""
    aliases: dict[str, set[str]] = {
        "辽宁": {"东北"}, "吉林": {"东北"}, "黑龙江": {"东北"}, "内蒙古": {"东北"},
        "上海": {"江苏", "浙江"}, "天津": {"北京"}, "河北": {"北京"},
        "重庆": {"四川"}, "宁夏": {"新疆"}, "青海": {"甘肃"}, "海南": {"广东"},
        "香港": {"广东"}, "澳门": {"广东"}, "台湾": {"福建"},
    }
    tags = {province, "通用"} if province else {"通用"}
    tags |= aliases.get(province, set())
    return tags


def _candidates(db: Session, cfg: AppConfig) -> list[Dish]:
    rows = db.execute(select(Dish).where(Dish.enabled.is_(True))).scalars().all()
    allowed = province_tags(cfg.province)
    out: list[Dish] = [dish for dish in rows if dish.province in allowed]
    if len(out) < 8:  # 该省数据太少就放宽到全库
        out = list(rows)
    return out


def compose_fallback(
    db: Session,
    cfg: AppConfig,
    *,
    target: date,
    count: int,
    recent: set[str],
    rng: random.Random | None = None,
) -> dict:
    """用本地库拼一份一定合规的菜单。

    默认每次用全新随机数，保证点「换一桌」真的会换 —— 之前用日期做种子导致重生成等于没点。
    需要可复现结果（测试用）时把 rng 传进来即可。
    """
    rng = rng or random.Random()
    pool = _candidates(db, cfg)

    def usable(dish: Dish, extra_recent: set[str]) -> bool:
        data = _dish_dict(dish)
        if data["name"] in extra_recent:
            return False
        return not (check_avoided(cfg, data) or check_spicy(cfg, data) or check_health(cfg, data))

    picked_names: set[str] = set(recent)

    def take(category: str, n: int, *, soft_repeat: bool = False) -> list[Dish]:
        found: list[Dish] = []
        buckets: list[list[Dish]] = [
            [d for d in pool if d.category == category and dish_matches_season(d.season, target)],
            [d for d in pool if d.category == category],
        ]
        for bucket in buckets:
            rng.shuffle(bucket)
            for dish in bucket:
                if len(found) >= n:
                    break
                if dish.name in picked_names:
                    continue
                if not soft_repeat and not usable(dish, picked_names):
                    continue
                found.append(dish)
                picked_names.add(dish.name)
            if len(found) >= n:
                break
        return found

    n_meat = max(1, round(count * 0.45)) if cfg.require_meat_and_veg else max(0, round(count * 0.4))
    n_veg = max(1, count - n_meat) if cfg.require_meat_and_veg else max(0, count - n_meat)

    chosen: list[Dish] = []
    chosen.extend(take(MEAT, n_meat))
    chosen.extend(take(VEG, n_veg))
    if len(chosen) < count:
        chosen.extend(take(COLD, count - len(chosen), soft_repeat=True))
    if len(chosen) < count:
        chosen.extend(take(MEAT, count - len(chosen), soft_repeat=True))
    if len(chosen) < count:
        chosen.extend(take(VEG, count - len(chosen), soft_repeat=True))
    if not chosen:  # 极端情况：库是空的
        return {
            "dishes": [],
            "soup": "",
            "staple": cfg.staple,
            "reason": "本地库为空，请先导入菜谱或检查 LLM 配置。",
            "status": "failed",
        }

    dishes: list[dict] = []
    for dish in chosen[:count]:
        data = _dish_dict(dish)
        dishes.append(
            {
                "name": data["name"],
                "category": data["category"],
                "ingredients": data["ingredients"],
                "tags": data["tags"],
                "spicy": data["spicy"],
                # note 是「一句话做法要点」，和 LLM 生成的菜单字段保持一致，UI 与推送共用
                "note": data["howto"],
                "steps": data["steps"],
            }
        )
    soup = ""
    if cfg.include_soup:
        soups = take(SOUP, 1, soft_repeat=True)
        if soups:
            soup = soups[0].name

    return {
        "dishes": dishes,
        "soup": soup,
        "staple": cfg.staple,
        "reason": "本地菜谱库按荤素与时令搭配，已通过重复与忌口校验。",
        "status": "fallback",
    }
