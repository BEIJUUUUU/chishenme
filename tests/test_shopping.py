"""购物清单与提示词测试。"""
from __future__ import annotations

from datetime import date

from app.core import shopping
from app.core.prompt import build_menu_messages
from app.runtime_config import AppConfig


def test_classify():
    assert shopping.classify("五花肉") == "肉蛋类"
    assert shopping.classify("基围虾") == "水产海鲜"
    assert shopping.classify("西兰花") == "蔬菜"
    assert shopping.classify("豆腐") == "豆制品"
    assert shopping.classify("生抽") == "调味料"
    assert shopping.classify("某个奇怪东西") == "其他"


def test_aggregate_counts_and_groups():
    dishes = [
        {"name": "西红柿炒鸡蛋", "ingredients": ["西红柿", "鸡蛋"]},
        {"name": "番茄牛腩", "ingredients": ["西红柿", "牛腩"]},
    ]
    result = shopping.aggregate(dishes, extra=["米饭"])
    flat = {item["name"]: item["count"] for group in result for item in group["items"]}
    assert flat["西红柿"] == 2
    assert flat["鸡蛋"] == 1
    assert "主食粮油" in [g["category"] for g in result]


def test_to_text():
    text = shopping.to_text(shopping.aggregate([{"name": "x", "ingredients": ["土豆", "青椒"]}]))
    assert "土豆" in text and "蔬菜" in text


def test_prompt_contains_constraints():
    cfg = AppConfig(
        province="四川",
        city="成都",
        health_flags=["痛风"],
        avoid_ingredients=["香菜"],
        spicy=1,
        likes="回锅肉",
        extra_note="周末要有硬菜",
    )
    messages = build_menu_messages(
        cfg, target=date(2024, 7, 10), meals=["午餐", "晚餐"], recent={"红烧肉"}, counts={"午餐": 4, "晚餐": 4}
    )
    user = messages[1]["content"]
    assert "四川成都" in user
    assert "痛风" in user
    assert "香菜" in user
    assert "红烧肉" in user
    assert "午餐" in user and "晚餐" in user
    assert "JSON" in messages[0]["content"] or "json" in messages[0]["content"]


def test_json_extraction_from_messy_output():
    from app.llm.json_utils import coerce_str_list, extract_json

    messy = '当然可以！\n```json\n{"meals": [{"meal": "午餐", "dishes": [{"name": "西红柿炒蛋"}]}]}\n```\n希望有帮助'
    data = extract_json(messy)
    assert data["meals"][0]["meal"] == "午餐"

    assert coerce_str_list("土豆、青椒，鸡蛋") == ["土豆", "青椒", "鸡蛋"]
    assert coerce_str_list(["土豆", "青椒"]) == ["土豆", "青椒"]
    assert coerce_str_list(None) == []
