"""菜谱库校验与兜底逻辑测试。"""
from __future__ import annotations

from datetime import date

from app.core import pantry
from app.runtime_config import AppConfig


def test_seed_and_compose(db, cfg):
    pantry.seed_database(db)
    from sqlalchemy import func, select

    from app.models import Dish

    total = db.execute(select(func.count()).select_from(Dish)).scalar_one()
    assert total > 50

    result = pantry.compose_fallback(
        db, cfg, target=date(2024, 7, 10), count=4, recent=set()
    )
    names = [d["name"] for d in result["dishes"]]
    assert len(names) == 4
    assert result["soup"]
    assert result["status"] == "fallback"


def test_compose_avoids_ingredients(db):
    from app.core.pantry import seed_database

    seed_database(db)
    cfg = AppConfig(province="山东", avoid_ingredients=["豆腐", "花生"])
    result = pantry.compose_fallback(db, cfg, target=date(2024, 7, 10), count=4, recent=set())
    for dish in result["dishes"]:
        for ingredient in dish["ingredients"]:
            assert "豆腐" not in ingredient
            assert "花生" not in ingredient


def test_validate_detects_repeat_and_balance(cfg):
    recent = {"红烧肉"}
    dishes = [
        {"name": "红烧肉", "category": "荤菜", "ingredients": ["五花肉"], "spicy": 0},
        {"name": "清蒸鲈鱼", "category": "荤菜", "ingredients": ["鲈鱼"], "spicy": 0},
    ]
    issues = pantry.validate_meal(
        cfg, dishes, target=date(2024, 7, 10), recent=recent, expected_count=2, soup=""
    )
    codes = {i["code"] for i in issues}
    assert "repeat" in codes
    assert "balance" in codes  # 全是荤菜
    assert pantry.errors_of(issues)


def test_validate_spicy_limit():
    cfg = AppConfig(spicy=1)
    dishes = [
        {"name": "水煮肉片", "category": "荤菜", "ingredients": ["猪肉"], "spicy": 3},
        {"name": "清炒西兰花", "category": "素菜", "ingredients": ["西兰花"], "spicy": 0},
    ]
    issues = pantry.validate_meal(
        cfg, dishes, target=date(2024, 7, 10), recent=set(), expected_count=2
    )
    assert any(i["code"] == "spicy" and i["level"] == "error" for i in issues)


def test_health_flag_blocks_seafood():
    cfg = AppConfig(health_flags=["痛风"])
    dishes = [
        {"name": "蒜蓉粉丝蒸虾", "category": "荤菜", "ingredients": ["基围虾"], "tags": ["海鲜"], "spicy": 0},
        {"name": "清炒西兰花", "category": "素菜", "ingredients": ["西兰花"], "spicy": 0},
    ]
    issues = pantry.validate_meal(
        cfg, dishes, target=date(2024, 7, 10), recent=set(), expected_count=2
    )
    assert any(i["code"] == "health" and i["level"] == "error" for i in issues)


def test_high_blood_pressure_blocks_cured_meat():
    cfg = AppConfig(health_flags=["高血压"])
    dishes = [{"name": "腊肉炒蒜苗", "category": "荤菜", "ingredients": ["腊肉"], "spicy": 0}]
    issues = pantry.validate_meal(
        cfg, dishes, target=date(2024, 7, 10), recent=set(), expected_count=1, soup=""
    )
    assert any(i["code"] == "health" for i in issues)


def test_season_warning_is_soft(cfg):
    cfg.strict_season = True
    dishes = [
        {"name": "凉拌黄瓜", "category": "凉菜", "season": "夏", "ingredients": ["黄瓜"], "spicy": 0},
        {"name": "红烧肉", "category": "荤菜", "season": "四季", "ingredients": ["五花肉"], "spicy": 0},
    ]
    issues = pantry.validate_meal(
        cfg, dishes, target=date(2024, 1, 15), recent=set(), expected_count=2, soup="汤"
    )
    season_issues = [i for i in issues if i["code"] == "season"]
    assert season_issues
    assert all(i["level"] == "warn" for i in season_issues)
