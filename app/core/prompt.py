"""提示词构造。

原则：
1. 把「家庭画像 + 时令 + 最近吃过的菜」全部塞进上下文，减少幻觉与重复。
2. 明确输出 JSON Schema，配合 response_format=json_object。
3. 校验失败时用 repair 提示词做定点修复，而不是重新随机生成（省 token、更稳）。
"""
from __future__ import annotations

from datetime import date

from ..runtime_config import AppConfig
from . import pantry
from .season import season_label, season_tip, seasonal_ingredients

SYSTEM_PROMPT = """你是一位中国家常菜营养搭配师，服务对象是普通家庭的老人和上班族。

你的任务：为一家人设计当天的中餐和晚餐菜单，要求
1. 符合指定省份菜系的真实做法与叫法，不要编造不存在的菜名。
2. 荤素搭配合理、口味有层次（有清淡有下饭）、做法不重复（不要全是炖菜或全是炒菜）。
3. 优先使用当季食材，食材在普通菜市场或超市能买到。
4. 尊重健康约束和忌口，这是硬性要求。
5. 每道菜给出 2~5 个主要食材（用于生成购物清单）。

只输出 JSON，不要输出任何解释文字、不要使用 markdown 代码块。"""

OUTPUT_SCHEMA_HINT = """输出 JSON 格式（严格遵守，不要增删字段）：
{
  "meals": [
    {
      "meal": "午餐",
      "dishes": [
        {"name": "菜名", "category": "荤菜", "ingredients": ["食材1", "食材2"], "spicy": 0, "note": "一句话做法要点"}
      ],
      "soup": "汤名，没有则空字符串",
      "staple": "主食",
      "reason": "一句话说明这桌菜的搭配思路"
    }
  ]
}
约束：
- category 只能是 荤菜 / 素菜 / 凉菜 / 汤 之一（主食请填在 staple 字段，不要放进 dishes）。
- spicy 为 0~3 的整数：0 不辣、1 微辣、2 中辣、3 重辣。
- dishes 数量必须严格等于要求数量。"""


def family_profile(cfg: AppConfig) -> str:
    lines = [
        f"- 家庭：{cfg.family_name}，{cfg.people} 人吃饭",
        f"- 地域菜系：{cfg.province}{cfg.city or ''}",
        f"- 辣度上限：{cfg.spicy}（0 不辣 ~ 3 重辣）",
        f"- 主食偏好：{cfg.staple}",
    ]
    if cfg.lunch_count or cfg.dinner_count:
        lines.append(f"- 午餐菜数：{cfg.lunch_count} 道菜（不含汤/主食）")
        lines.append(f"- 晚餐菜数：{cfg.dinner_count} 道菜（不含汤/主食）")
    if cfg.include_soup:
        lines.append("- 每餐配一个汤")
    if cfg.budget:
        lines.append(f"- 单餐预算：约 {cfg.budget} 元")
    if cfg.likes:
        lines.append(f"- 家人爱吃：{cfg.likes}")
    if cfg.dislikes:
        lines.append(f"- 家人不爱吃（不要出现）：{cfg.dislikes}")
    if cfg.avoid_ingredients:
        lines.append(f"- 忌口食材（绝对不要出现，含配菜与调味）：{'、'.join(cfg.avoid_ingredients)}")
    if cfg.health_flags:
        lines.append(f"- 健康约束（必须遵守）：{'、'.join(cfg.health_flags)}")
    if cfg.extra_note:
        lines.append(f"- 额外要求：{cfg.extra_note}")
    return "\n".join(lines)


def build_menu_messages(
    cfg: AppConfig,
    *,
    target: date,
    meals: list[str],
    recent: set[str],
    counts: dict[str, int],
) -> list[dict[str, str]]:
    weekday = "一二三四五六日"[target.weekday()]
    seasonal = "、".join(seasonal_ingredients(target)[:14])
    recent_text = "、".join(sorted(recent)[:60]) if recent else "（无记录）"

    meal_lines = []
    for meal in meals:
        meal_lines.append(f"- {meal}：{counts.get(meal, cfg.lunch_count)} 道菜")

    user = f"""请为下面这个家庭设计 {target.isoformat()}（星期{weekday}）的菜单。

【家庭画像】
{family_profile(cfg)}

【时令信息】
- 当前季节：{season_label(target)}（{season_tip(target)}）
- 当季推荐食材：{seasonal or "（无数据）"}

【最近 {cfg.repeat_window_days} 天已经吃过的菜（严格不要重复）】
{recent_text}

【本次需要生成】
{chr(10).join(meal_lines)}
- 每个 meal 只生成一次，meal 字段必须严格使用「{"」「".join(meals)}」这几个值之一

{OUTPUT_SCHEMA_HINT}"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_repair_messages(
    cfg: AppConfig,
    *,
    target: date,
    previous: str,
    issues: list[dict],
    meals: list[str],
    counts: dict[str, int],
    recent: set[str],
) -> list[dict[str, str]]:
    problems = pantry.issue_text(issues)
    problem_lines = "\n".join(f"{i+1}. {p}" for i, p in enumerate(problems))
    recent_text = "、".join(sorted(recent)[:60]) if recent else "（无记录）"
    meal_lines = "、".join(f"{m} {counts.get(m, cfg.lunch_count)} 道菜" for m in meals)

    user = f"""你上一次的输出没有通过校验，请修正后重新输出完整 JSON。

【上一次的输出】
{previous[:4000]}

【必须修复的问题（逐条解决）】
{problem_lines}

【不可违反的硬性要求】
{pantry.issue_text([
    {"message": f"忌口食材绝对不要出现：{'、'.join(cfg.avoid_ingredients)}"} if cfg.avoid_ingredients else {"message": "无额外忌口"},
    {"message": f"健康约束：{'、'.join(cfg.health_flags)}"} if cfg.health_flags else {"message": "无健康约束"},
    {"message": f"辣度不得超过 {cfg.spicy}"},
    {"message": f"最近吃过、不得重复：{recent_text}"},
])}

【本次需要生成】{meal_lines}

请只输出修正后的完整 JSON（格式同上次，不要解释）。"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_single_meal_messages(cfg: AppConfig, *, target: date, meal: str, recent: set[str]) -> list[dict[str, str]]:
    count = cfg.lunch_count if meal == "午餐" else cfg.dinner_count
    return build_menu_messages(
        cfg, target=target, meals=[meal], recent=recent, counts={meal: count}
    )
