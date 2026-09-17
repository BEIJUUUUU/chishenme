"""时令计算。"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SEASON_BY_MONTH = {
    1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春",
    6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋", 12: "冬",
}

SEASON_LABEL = {"春": "春季", "夏": "夏季", "秋": "秋季", "冬": "冬季"}
SEASON_TIP = {
    "春": "春季宜清淡养肝，多绿叶菜与芽菜",
    "夏": "夏季宜清热解暑，多瓜类与凉拌菜",
    "秋": "秋季宜润燥，多莲藕、山药、梨、银耳",
    "冬": "冬季宜温补，多炖菜、根茎类与热汤",
}


@lru_cache
def _seasonal_table() -> dict[str, list[str]]:
    path = DATA_DIR / "seasonal.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def season_of(target: date | None = None) -> str:
    target = target or date.today()
    return SEASON_BY_MONTH.get(target.month, "四季")


def season_label(target: date | None = None) -> str:
    return SEASON_LABEL[season_of(target)]


def season_tip(target: date | None = None) -> str:
    return SEASON_TIP[season_of(target)]


def seasonal_ingredients(target: date | None = None) -> list[str]:
    target = target or date.today()
    return _seasonal_table().get(str(target.month), [])


def dish_matches_season(dish_season: str, target: date | None = None) -> bool:
    """菜品的 season 字段形如 '四季' / '夏' / '夏,秋'。"""
    if not dish_season or "四季" in dish_season:
        return True
    current = season_of(target)
    return current in [s.strip() for s in dish_season.split(",")]
