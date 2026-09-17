"""生成编排测试：用假的 LLM 验证「生成 → 校验 → 打回 → 兜底」全链路。"""
from __future__ import annotations

from datetime import date

import pytest

from app.core import generator, pantry
from app.llm.base import BaseLLM, LLMResult
from app.runtime_config import AppConfig


class FakeLLM(BaseLLM):
    """按脚本依次返回预设文本。"""

    provider = "fake"

    def __init__(self, config, responses):
        super().__init__(config)
        self.responses = list(responses)
        self.calls = 0

    @property
    def model(self):
        return "fake-model"

    async def chat(self, messages, *, json_mode=False):
        self.calls += 1
        text = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return LLMResult(text=text, provider=self.provider, model=self.model, elapsed_ms=1)


@pytest.fixture()
def patched(monkeypatch):
    def _install(responses):
        llm = FakeLLM(AppConfig(), responses)
        monkeypatch.setattr(generator, "build_llm", lambda config: llm)
        return llm

    return _install


@pytest.mark.asyncio
async def test_good_response_is_accepted(db, cfg, patched):
    pantry.seed_database(db)
    llm = patched([
        '{"meals":[{"meal":"午餐","dishes":['
        '{"name":"清蒸鲈鱼","category":"荤菜","ingredients":["鲈鱼","姜"],"spicy":0},'
        '{"name":"清炒西兰花","category":"素菜","ingredients":["西兰花","蒜"],"spicy":0}'
        '],"soup":"紫菜蛋花汤","staple":"米饭","reason":"清淡好消化"}]}'
    ])
    plans = await generator.generate_day(db, cfg, date(2024, 7, 10), meals=("午餐",))
    plan = plans["午餐"]
    assert plan.source == "llm"
    assert plan.status == "ok"
    assert plan.dish_names == ["清蒸鲈鱼", "清炒西兰花"]
    assert plan.soup == "紫菜蛋花汤"
    assert llm.calls == 1
    assert plan.shopping  # 购物清单已生成


@pytest.mark.asyncio
async def test_bad_then_repaired(db, cfg, patched):
    pantry.seed_database(db)
    cfg.llm_max_repair = 1
    llm = patched([
        # 第一次：重复菜 + 缺素菜
        '{"meals":[{"meal":"午餐","dishes":['
        '{"name":"红烧肉","category":"荤菜","ingredients":["五花肉"],"spicy":0}'
        '],"soup":"紫菜蛋花汤","staple":"米饭"}]}',
        # 第二次：修好了
        '{"meals":[{"meal":"午餐","dishes":['
        '{"name":"清蒸鲈鱼","category":"荤菜","ingredients":["鲈鱼"],"spicy":0},'
        '{"name":"香菇油菜","category":"素菜","ingredients":["香菇","油菜"],"spicy":0}'
        '],"soup":"番茄鸡蛋汤","staple":"米饭"}]}',
    ])
    plans = await generator.generate_day(
        db, cfg, date(2024, 7, 10), meals=("午餐",), force=True
    )
    assert llm.calls == 2
    assert plans["午餐"].source == "llm"
    assert "香菇油菜" in plans["午餐"].dish_names


@pytest.mark.asyncio
async def test_failure_falls_back_to_local(db, cfg, patched):
    pantry.seed_database(db)
    cfg.llm_max_repair = 0
    patched(["这不是 JSON，只是胡说八道。"])
    plans = await generator.generate_day(
        db, cfg, date(2024, 7, 10), meals=("午餐",), force=True
    )
    plan = plans["午餐"]
    assert plan.source == "local"
    assert plan.status == "fallback"
    assert plan.dishes
    assert plan.issues


@pytest.mark.asyncio
async def test_repeat_window_blocks_previous_dish(db, cfg, patched):
    pantry.seed_database(db)
    cfg.repeat_window_days = 5

    # 先落一天的菜单
    generator.upsert_plan(
        db, cfg, date(2024, 7, 9), "午餐",
        {"dishes": [{"name": "红烧肉", "category": "荤菜", "ingredients": ["五花肉"], "spicy": 0},
                    {"name": "醋溜土豆丝", "category": "素菜", "ingredients": ["土豆"], "spicy": 0}],
         "soup": "紫菜蛋花汤", "staple": "米饭", "reason": ""},
        source="llm",
    )

    recent = pantry.recent_dish_names(db, date(2024, 7, 10), 5)
    assert "红烧肉" in recent

    issues = pantry.check_repeat(recent, {"name": "红烧肉"})
    assert issues and issues[0]["code"] == "repeat"
