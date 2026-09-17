#!/usr/bin/env python
"""离线演示：不需要任何 LLM API Key，直接用本地菜谱库排一桌并打印。

    python scripts/offline_demo.py

用途：
1. 验证部署是否正常（数据库、菜谱库、购物清单、消息渲染）。
2. 没配 LLM 时先看看效果，再决定要不要接大模型。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.generator import upsert_plan
from app.core.message import day_markdown, day_plain
from app.core.pantry import seed_database
from app.core.season import season_label, season_tip
from app.db import init_db, session_scope
from app.notify import channel_choices
from app.runtime_config import load_config


def main() -> None:
    target = date.today()
    init_db()

    with session_scope() as db:
        added = seed_database(db)
        cfg = load_config(db)

        print("=== 吃什么？离线演示 ===")
        print(f"家庭：{cfg.family_name} · {cfg.province}{cfg.city} · {cfg.people} 人")
        print(f"今天：{target.isoformat()} · {season_label(target)} · {season_tip(target)}")
        if added:
            print(f"（首次运行，已导入内置菜谱 {added} 道）")
        print(f"LLM 通道：{cfg.llm_mode} · 推送通道：{cfg.push_channels or '未配置'}")
        print(f"可选推送通道：{', '.join(f'{k}({v})' for k, v in channel_choices())}")
        print()

        # 用本地库兜底逻辑直接排菜（不走 LLM）
        from app.core.pantry import compose_fallback, recent_dish_names

        recent = recent_dish_names(db, target, cfg.repeat_window_days)
        plans = []
        for meal, count in (("午餐", cfg.lunch_count), ("晚餐", cfg.dinner_count)):
            data = compose_fallback(db, cfg, target=target, count=count, recent=recent)
            plan = upsert_plan(
                db, cfg, target, meal, data, source="local", status="demo", model="local-library"
            )
            recent.update(plan.all_dish_names)
            plans.append(plan)

        print(day_plain(plans, title="🍚 离线演示菜单", family=cfg.family_name))
        print()
        print("--- 以下是推送到微信时用的 markdown ---")
        print(
            day_markdown(
                plans,
                title="🍚 离线演示菜单",
                family=cfg.family_name,
                with_steps=cfg.push_with_steps,
            )
        )


if __name__ == "__main__":
    main()
