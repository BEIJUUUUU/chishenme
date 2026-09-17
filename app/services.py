"""推送服务：组装消息 → 多通道发送 → 落库。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.message import day_markdown, day_plain
from .models import Plan, PushLog
from .notify import send_all, send_to_channel
from .runtime_config import AppConfig


def load_plans(db: Session, target: date, meals: tuple[str, ...] = ("午餐", "晚餐")) -> list[Plan]:
    rows = (
        db.execute(select(Plan).where(Plan.plan_date == target).order_by(Plan.id))
        .scalars()
        .all()
    )
    order = {meal: idx for idx, meal in enumerate(meals)}
    return sorted(rows, key=lambda p: order.get(p.meal, 99))


def build_title(cfg: AppConfig, target: date, meals: tuple[str, ...]) -> str:
    prefix = cfg.push_title_prefix or "🍚 今日菜单"
    scope = " + ".join(meals)
    when = "今天" if target == date.today() else f"{target.month}月{target.day}日"
    return f"{prefix} · {when} {scope}"


async def push_day(
    db: Session,
    cfg: AppConfig,
    target: date,
    *,
    meals: tuple[str, ...] = ("午餐", "晚餐"),
    channels: list[str] | None = None,
    with_shopping: bool = True,
    extra_note: str = "",
) -> list[dict]:
    plans = load_plans(db, target, meals)
    plans = [p for p in plans if p.meal in meals]
    if not plans:
        return []

    title = build_title(cfg, target, tuple(p.meal for p in plans))
    markdown = day_markdown(
        plans, title=title, family=cfg.family_name, extra_note=extra_note,
        with_steps=cfg.push_with_steps,
    )
    plain = day_plain(
        plans, title=title, family=cfg.family_name, extra_note=extra_note,
        with_steps=cfg.push_with_steps,
    )
    if not with_shopping:
        markdown = markdown.split("## 🛒 买菜清单")[0].strip()
        plain = plain.split("🛒 买菜清单")[0].strip()

    results = await send_all(cfg, title, markdown, plain, channels)

    for result in results:
        db.add(
            PushLog(
                plan_id=plans[0].id,
                channel=result.channel,
                target=result.target or "",
                ok=result.ok,
                title=title,
                message=result.message[:500],
            )
        )
    if any(r.ok for r in results):
        stamp = datetime.now()
        for plan in plans:
            plan.pushed_at = stamp
    db.commit()

    return [r.as_dict() for r in results]


async def send_test_message(db: Session, cfg: AppConfig, channel: str) -> dict:
    title = "🍚 吃什么？· 通道测试"
    markdown = "# 🍚 吃什么？测试消息\n\n如果你看到这条消息，说明推送通道配置正确。\n\n- 今天是测试，不会影响正式菜单\n- 正式推送会包含中晚餐菜单 + 买菜清单"
    plain = "🍚 吃什么？测试消息\n\n通道配置正确，正式推送会包含菜单和买菜清单。"
    result = await send_to_channel(channel, title, markdown, plain, cfg)
    db.add(
        PushLog(
            channel=channel,
            ok=result.ok,
            title=title,
            message=(result.message or "")[:500],
        )
    )
    db.commit()
    return result.as_dict()
