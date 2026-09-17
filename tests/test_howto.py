"""做法库测试：覆盖率、随菜单带出、推送渲染。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.core import pantry
from app.core.message import day_markdown, day_plain, recipes_markdown, recipe_of
from app.models import Dish


def test_every_seed_dish_has_howto():
    """菜谱库里的每道菜都必须有做法，否则默认模式等于只给菜名。"""
    dishes = pantry.load_seed_dishes()
    howto = pantry.load_howto()
    assert dishes, "菜谱库不该为空"

    missing = [d["name"] for d in dishes if d["name"] not in howto]
    assert missing == [], f"这些菜缺做法：{missing}"

    for name, recipe in howto.items():
        assert recipe.get("howto", "").strip(), f"{name} 缺一句话做法要点"
        assert recipe.get("steps", "").strip(), f"{name} 缺三步做法"
        assert "①" in recipe["steps"], f"{name} 的做法步骤应写成 ①②③ 形式"


def test_howto_has_no_orphan_entries():
    howto = pantry.load_howto()
    names = {d["name"] for d in pantry.load_seed_dishes()}
    assert [n for n in howto if n not in names] == []


def test_seed_writes_howto_into_database(db):
    pantry.seed_database(db)
    total = db.execute(select(func.count()).select_from(Dish)).scalar_one()
    with_howto = db.execute(
        select(func.count()).select_from(Dish).where(Dish.howto != "")
    ).scalar_one()
    assert with_howto == total, "导入后每道菜都应带做法"

    sample = db.execute(select(Dish).where(Dish.name == "红烧肉")).scalar_one()
    assert "冰糖" in sample.howto or "炖" in sample.howto
    assert "①" in sample.steps


def test_seed_backfills_howto_for_existing_rows(db):
    """老库升级场景：已经有菜但没做法，重新 seed 应该把做法补上。"""
    pantry.seed_database(db)

    # 模拟老库：把某道菜的做法清空
    dish = db.execute(select(Dish).where(Dish.name == "红烧肉")).scalar_one()
    dish.howto = ""
    dish.steps = ""
    db.commit()

    # 自己加的菜，做法库里没有，seed 不能瞎编
    db.add(Dish(name="自创测试菜", province="通用", category="荤菜", season="四季", ingredients=["土豆"]))
    db.commit()

    pantry.seed_database(db)

    refreshed = db.execute(select(Dish).where(Dish.name == "红烧肉")).scalar_one()
    assert refreshed.howto and refreshed.steps, "同名菜缺做法时应从做法库补上"

    homemade = db.execute(select(Dish).where(Dish.name == "自创测试菜")).scalar_one()
    assert homemade.howto == "" and homemade.steps == ""

    # 清掉测试菜，免得被后面的兜底拼菜选中（共享同一个测试库）
    db.delete(homemade)
    db.commit()


def test_schema_migration_adds_missing_columns():
    """老库直接升级：缺列会被自动补上，不用删库重来。"""
    import os
    from pathlib import Path

    from sqlalchemy import create_engine

    from app.db import ensure_schema

    db_file = Path(os.environ["CSM_DATA_DIR"]) / "legacy-migration.db"
    if db_file.exists():
        db_file.unlink()
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE dishes (id INTEGER PRIMARY KEY, name TEXT)")
        connection.exec_driver_sql("CREATE TABLE plans (id INTEGER PRIMARY KEY, plan_date DATE)")

    ensure_schema(engine)
    ensure_schema(engine)  # 幂等，重复执行不能报错

    with engine.begin() as connection:
        dish_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(dishes)")}
        plan_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(plans)")}

    assert {"howto", "steps"} <= dish_columns
    assert "recipes" in plan_columns
    engine.dispose()


def test_local_menu_carries_howto_and_steps(db, cfg):
    pantry.seed_database(db)
    result = pantry.compose_fallback(db, cfg, target=date(2024, 7, 10), count=4, recent=set())
    assert result["status"] == "fallback"
    for dish in result["dishes"]:
        assert dish["note"], f"{dish['name']} 应该带一句话做法要点"
        assert dish["steps"], f"{dish['name']} 应该带三步做法"


def test_plan_recipes_snapshot_and_rendering(db, cfg):
    from app.core.generator import upsert_plan

    pantry.seed_database(db)
    data = pantry.compose_fallback(db, cfg, target=date(2024, 7, 10), count=4, recent=set())
    plan = upsert_plan(db, cfg, date(2024, 7, 10), "午餐", data, source="local", status="local")

    assert plan.recipes, "生成时应固化做法快照"
    first = plan.dishes[0]["name"]
    assert plan.recipes[first]["steps"], f"{first} 的快照里应有步骤"
    assert plan.soup in plan.recipes

    md = day_markdown([plan], title="今日菜单", family="我家", with_steps=True)
    assert "👩‍🍳" in md
    assert first in md
    assert plan.recipes[first]["steps"] in md

    md_short = day_markdown([plan], title="今日菜单", with_steps=False)
    assert plan.recipes[first]["steps"] not in md_short

    plain = day_plain([plan], title="今日菜单", with_steps=True)
    assert plan.recipes[first]["steps"] in plain

    only_recipes = recipes_markdown([plan])
    assert first in only_recipes and plan.recipes[first]["steps"] in only_recipes


def test_recipe_of_falls_back_for_legacy_plans(db, cfg):
    """老数据没有 recipes 快照，也不能报错。"""
    from app.core.generator import upsert_plan

    plan = upsert_plan(
        db, cfg, date(2024, 7, 11), "午餐",
        {"dishes": [{"name": "某道菜", "category": "荤菜", "ingredients": ["土豆"], "note": "随便炒炒"}],
         "soup": "", "staple": "米饭", "reason": ""},
        source="manual",
    )
    plan.recipes = {}
    db.commit()

    assert recipe_of(plan, "某道菜") == {"howto": "", "steps": ""}
    md = day_markdown([plan], title="x", with_steps=True)
    assert "某道菜" in md  # 渲染不炸
