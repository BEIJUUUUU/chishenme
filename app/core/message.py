"""把 Plan 渲染成给老人看的文本：markdown（微信/飞书）与纯文本（Bark/短信式）。

设计目标：手机上一眼能看完，菜名在前、做法提示在后，购物清单分行归类。
"""
from __future__ import annotations

from datetime import date

from ..models import Plan

WEEKDAY_CN = "一二三四五六日"


def date_label(target: date, *, prefix: str = "") -> str:
    return f"{prefix}{target.isoformat()} 周{WEEKDAY_CN[target.weekday()]}"


def plan_lines(plan: Plan, *, bullet: str = "·") -> list[str]:
    lines: list[str] = []
    for dish in plan.dishes or []:
        name = dish.get("name", "")
        note = dish.get("note", "")
        if not name:
            continue
        lines.append(f"{bullet} {name}" + (f"（{note}）" if note else ""))
    if plan.soup:
        lines.append(f"{bullet} {plan.soup}")
    if plan.staple:
        lines.append(f"{bullet} 主食：{plan.staple}")
    return lines


def meal_plain(plan: Plan) -> str:
    head = f"【{plan.meal}】"
    body = "、".join(d.get("name", "") for d in (plan.dishes or []) if d.get("name"))
    if plan.soup:
        body += f"，{plan.soup}"
    line = f"{head}{body}"
    if plan.staple:
        line += f"\n   主食：{plan.staple}"
    if plan.reason:
        line += f"\n   💡 {plan.reason}"
    return line


def meal_markdown(plan: Plan) -> str:
    lines = [f"**{plan.meal}**"]
    for dish in plan.dishes or []:
        name = dish.get("name", "")
        if not name:
            continue
        note = dish.get("note", "")
        category = dish.get("category", "")
        lines.append(f"- {name}" + (f" · *{category}*" if category else "") + (f" —— {note}" if note else ""))
    if plan.soup:
        lines.append(f"- {plan.soup} · *汤*")
    if plan.staple:
        lines.append(f"- 主食：{plan.staple}")
    if plan.reason:
        lines.append(f"> {plan.reason}")
    return "\n".join(lines)


def shopping_plain(plans: list[Plan]) -> str:
    from .shopping import merge_plans, to_text

    return to_text(merge_plans(plans))


def day_markdown(plans: list[Plan], *, title: str, family: str = "", extra_note: str = "") -> str:
    if not plans:
        return f"{title}\n\n（今天还没有菜单，去 WebUI 生成一下吧）"
    target = plans[0].plan_date
    parts = [f"# {title}", f"*{date_label(target)} · {family}*" if family else f"*{date_label(target)}*", ""]
    for plan in plans:
        parts.append(meal_markdown(plan))
        parts.append("")
    shopping = shopping_plain(plans)
    if shopping:
        parts.append("## 🛒 买菜清单")
        parts.append(shopping)
        parts.append("")
    warnings = [w for plan in plans for w in (plan.issues or [])]
    if warnings:
        parts.append("## ⚠️ 生成提示")
        parts.extend(f"- {w}" for w in warnings[:6])
        parts.append("")
    if extra_note:
        parts.append(extra_note)
    return "\n".join(parts).strip()


def day_plain(plans: list[Plan], *, title: str, family: str = "", extra_note: str = "") -> str:
    if not plans:
        return f"{title}\n\n（今天还没有菜单）"
    target = plans[0].plan_date
    parts = [title, date_label(target) + (f" · {family}" if family else ""), ""]
    for plan in plans:
        parts.append(meal_plain(plan))
        parts.append("")
    shopping = shopping_plain(plans)
    if shopping:
        parts.append("🛒 买菜清单")
        parts.append(shopping)
        parts.append("")
    if extra_note:
        parts.append(extra_note)
    return "\n".join(parts).strip()


def shopping_list_text(plans: list[Plan]) -> str:
    return shopping_plain(plans)
