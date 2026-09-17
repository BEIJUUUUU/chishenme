"""把 Plan 渲染成给老人看的文本：markdown（微信/飞书）与纯文本（Bark/短信式）。

设计目标：手机上一眼能看完，菜名在前、做法紧跟；不需要做法时可以整体关掉。
"""
from __future__ import annotations

from datetime import date

from ..models import Plan

WEEKDAY_CN = "一二三四五六日"


def date_label(target: date, *, prefix: str = "") -> str:
    return f"{prefix}{target.isoformat()} 周{WEEKDAY_CN[target.weekday()]}"


def dish_names(plan: Plan) -> list[str]:
    names = [str(d.get("name", "")) for d in (plan.dishes or []) if d.get("name")]
    if plan.soup:
        names.append(plan.soup)
    return names


def recipe_of(plan: Plan, name: str) -> dict:
    """取做法快照。老数据没有快照时退回菜里的 note 字段。"""
    recipes = plan.recipes or {}
    entry = recipes.get(name)
    if isinstance(entry, dict):
        return {"howto": entry.get("howto", "") or "", "steps": entry.get("steps", "") or ""}
    return {"howto": "", "steps": ""}


def plan_lines(plan: Plan, *, bullet: str = "·") -> list[str]:
    lines: list[str] = []
    for dish in plan.dishes or []:
        name = dish.get("name", "")
        if not name:
            continue
        note = recipe_of(plan, name)["howto"] or dish.get("note", "")
        lines.append(f"{bullet} {name}" + (f"（{note}）" if note else ""))
    if plan.soup:
        note = recipe_of(plan, plan.soup)["howto"]
        lines.append(f"{bullet} {plan.soup}" + (f"（{note}）" if note else ""))
    if plan.staple:
        lines.append(f"{bullet} 主食：{plan.staple}")
    return lines


def meal_plain(plan: Plan, *, with_steps: bool = False) -> str:
    head = f"【{plan.meal}】"
    body = "、".join(d.get("name", "") for d in (plan.dishes or []) if d.get("name"))
    if plan.soup:
        body += f"，{plan.soup}"
    line = f"{head}{body}"
    if plan.staple:
        line += f"\n   主食：{plan.staple}"

    if with_steps:
        for name in dish_names(plan):
            steps = recipe_of(plan, name)["steps"]
            if steps:
                line += f"\n   · {name}：{steps}"

    if plan.reason:
        line += f"\n   💡 {plan.reason}"
    return line


def meal_markdown(plan: Plan, *, with_steps: bool = False) -> str:
    lines = [f"**{plan.meal}**"]
    for dish in plan.dishes or []:
        name = dish.get("name", "")
        if not name:
            continue
        note = recipe_of(plan, name)["howto"] or dish.get("note", "")
        category = dish.get("category", "")
        tail = f" —— {note}" if note else ""
        lines.append(f"- {name}" + (f" · *{category}*" if category else "") + tail)
    if plan.soup:
        note = recipe_of(plan, plan.soup)["howto"]
        lines.append(f"- {plan.soup} · *汤*" + (f" —— {note}" if note else ""))
    if plan.staple:
        lines.append(f"- 主食：{plan.staple}")
    if plan.reason:
        lines.append(f"> {plan.reason}")

    if with_steps:
        detailed = [(name, recipe_of(plan, name)["steps"]) for name in dish_names(plan)]
        detailed = [(name, steps) for name, steps in detailed if steps]
        if detailed:
            lines.append("")
            lines.append(f"*👩‍🍳 {plan.meal}简单做法*")
            for name, steps in detailed:
                lines.append(f"- **{name}**：{steps}")
    return "\n".join(lines)


def shopping_plain(plans: list[Plan]) -> str:
    from .shopping import merge_plans, to_text

    return to_text(merge_plans(plans))


def day_markdown(
    plans: list[Plan],
    *,
    title: str,
    family: str = "",
    extra_note: str = "",
    with_steps: bool = False,
) -> str:
    if not plans:
        return f"{title}\n\n（今天还没有菜单，去 WebUI 生成一下吧）"
    target = plans[0].plan_date
    parts = [f"# {title}", f"*{date_label(target)} · {family}*" if family else f"*{date_label(target)}*", ""]
    for plan in plans:
        parts.append(meal_markdown(plan, with_steps=with_steps))
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


def day_plain(
    plans: list[Plan],
    *,
    title: str,
    family: str = "",
    extra_note: str = "",
    with_steps: bool = False,
) -> str:
    if not plans:
        return f"{title}\n\n（今天还没有菜单）"
    target = plans[0].plan_date
    parts = [title, date_label(target) + (f" · {family}" if family else ""), ""]
    for plan in plans:
        parts.append(meal_plain(plan, with_steps=with_steps))
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


def recipes_markdown(plans: list[Plan]) -> str:
    """只输出做法，方便在 WebUI 里单独复制。"""
    lines: list[str] = []
    for plan in plans:
        lines.append(f"【{plan.meal}】")
        for name in dish_names(plan):
            recipe = recipe_of(plan, name)
            if recipe["steps"]:
                lines.append(f"{name}：{recipe['steps']}")
            elif recipe["howto"]:
                lines.append(f"{name}：{recipe['howto']}")
        lines.append("")
    return "\n".join(lines).strip()
