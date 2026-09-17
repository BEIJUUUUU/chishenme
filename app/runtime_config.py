"""家庭运行期配置：Pydantic 模型 + WebUI 表单 Schema + 读写。

设计要点：
- 单一 AppConfig 模型是全部可配置项的真源（source of truth）。
- SETTINGS_SCHEMA 描述「怎么在页面上渲染与解析」，页面模板完全数据驱动，
  新增一个配置项只需要改这两个地方之一。
- 存储为 settings 表的 key-value（value 是 JSON 片段），便于迁移与部分更新。
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Setting

PROVINCES: list[str] = [
    "通用", "北京", "天津", "河北", "山西", "内蒙古",
    "辽宁", "吉林", "黑龙江", "上海", "江苏", "浙江",
    "安徽", "福建", "江西", "山东", "河南", "湖北",
    "湖南", "广东", "广西", "海南", "重庆", "四川",
    "贵州", "云南", "西藏", "陕西", "甘肃", "青海",
    "宁夏", "新疆", "香港", "澳门", "台湾",
]

HEALTH_FLAGS: list[str] = ["高血压", "高血糖", "高血脂", "痛风", "胃不好", "牙口不好", "忌辛辣", "术后恢复"]

CATEGORIES: list[str] = ["荤菜", "素菜", "汤", "凉菜", "主食"]


class AppConfig(BaseModel):
    """全部家庭配置。字段名 = settings 表里的 key。"""

    # ---------- 访问控制 ----------
    auth_mode: Literal["none", "password"] = "none"

    # ---------- 家庭画像 ----------
    family_name: str = "我家"
    province: str = "山东"
    city: str = ""
    people: int = Field(default=4, ge=1, le=20)
    lunch_count: int = Field(default=4, ge=1, le=8, description="午餐菜品数（不含汤/主食）")
    dinner_count: int = Field(default=4, ge=1, le=8, description="晚餐菜品数（不含汤/主食）")
    include_soup: bool = True
    staple: str = "米饭"
    spicy: int = Field(default=1, ge=0, le=3, description="家庭辣度上限 0=不辣 3=重辣")
    budget: int = Field(default=80, ge=0, le=2000, description="单餐预算（元），0 表示不限")

    # ---------- 口味偏好 ----------
    likes: str = ""
    dislikes: str = ""
    avoid_ingredients: list[str] = Field(default_factory=list)
    health_flags: list[str] = Field(default_factory=list)

    # ---------- LLM（可不配置：默认只用本地菜谱库）----------
    llm_mode: Literal["off", "openai", "ollama"] = "off"
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_api_key: str = ""
    openai_model: str = "deepseek-chat"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_temperature: float = Field(default=0.85, ge=0.0, le=2.0)
    llm_timeout: int = Field(default=150, ge=10, le=900)
    llm_max_repair: int = Field(default=2, ge=0, le=5)
    llm_json_mode: bool = True

    # ---------- 校验规则 ----------
    repeat_window_days: int = Field(default=5, ge=0, le=60, description="N 天内不重复出现同一道菜")
    require_meat_and_veg: bool = True
    strict_season: bool = True

    # ---------- 推送 ----------
    scheduler_enabled: bool = True
    lunch_push_time: str = "07:30"
    dinner_push_time: str = "15:30"
    push_days_ahead: int = Field(default=0, ge=0, le=7)
    push_channels: list[str] = Field(default_factory=lambda: ["wecom"])
    push_title_prefix: str = "🍚 今日菜单"
    push_with_steps: bool = True

    wecom_webhook: str = ""
    serverchan_key: str = ""
    pushplus_token: str = ""
    pushplus_topic: str = ""
    wxpusher_app_token: str = ""
    wxpusher_uid: str = ""
    feishu_webhook: str = ""
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""
    bark_url: str = ""
    custom_webhook: str = ""

    # ---------- 其他 ----------
    extra_note: str = Field(default="", description="每次生成都会附带的额外要求")


# --------------------------------------------------------------------------------------
# 表单 Schema：type 决定渲染控件与解析方式
# --------------------------------------------------------------------------------------
SETTINGS_SCHEMA: list[dict[str, Any]] = [
    {
        "group": "家庭画像",
        "icon": "🏠",
        "hint": "决定菜系口味与菜量，至少把省份和人数填对。",
        "fields": [
            {"key": "family_name", "label": "家庭名称", "type": "text", "placeholder": "我家"},
            {"key": "province", "label": "省份 / 菜系", "type": "select", "choices": PROVINCES,
             "hint": "决定默认菜系，如 山东 → 鲁菜、四川 → 川菜"},
            {"key": "city", "label": "城市（选填）", "type": "text", "placeholder": "青岛",
             "hint": "填了会让 LLM 更贴近本地食材与做法"},
            {"key": "people", "label": "吃饭人数", "type": "number", "min": 1, "max": 20},
            {"key": "lunch_count", "label": "午餐菜品数", "type": "number", "min": 1, "max": 8,
             "hint": "不含汤和主食。4 人家庭一般 3~4 个菜"},
            {"key": "dinner_count", "label": "晚餐菜品数", "type": "number", "min": 1, "max": 8},
            {"key": "include_soup", "label": "配一个汤", "type": "bool"},
            {"key": "staple", "label": "主食", "type": "text", "placeholder": "米饭 / 馒头 / 面条"},
            {"key": "spicy", "label": "辣度上限", "type": "select",
             "choices": [(0, "0 · 完全不吃辣"), (1, "1 · 微辣"), (2, "2 · 中辣"), (3, "3 · 重辣")]},
            {"key": "budget", "label": "单餐预算（元）", "type": "number", "min": 0, "max": 2000,
             "hint": "0 表示不限"},
        ],
    },
    {
        "group": "口味与健康",
        "icon": "❤️",
        "hint": "老人常见三高、痛风、牙口问题在这里勾选，生成时会自动避开。",
        "fields": [
            {"key": "likes", "label": "爱吃的", "type": "textarea", "placeholder": "炖菜、清蒸鱼、面食"},
            {"key": "dislikes", "label": "不爱吃的", "type": "textarea", "placeholder": "苦瓜、香菜"},
            {"key": "avoid_ingredients", "label": "忌口食材", "type": "tags",
             "placeholder": "每行一个，或用逗号分隔：\n花生\n海鲜\n内脏"},
            {"key": "health_flags", "label": "健康约束", "type": "checkboxes", "choices": HEALTH_FLAGS},
            {"key": "extra_note", "label": "每日额外要求", "type": "textarea",
             "placeholder": "例：周二周四吃素；周末要有一道硬菜", "hint": "会附加到每次生成的提示词里"},
        ],
    },
    {
        "group": "LLM 模型",
        "icon": "🤖",
        "hint": "默认「仅本地菜谱库」，不用填任何密钥就能用。想让 AI 按你的口味自由配菜，再选下面两个通道之一并点「测试连接」。",
        "fields": [
            {"key": "llm_mode", "label": "通道", "type": "select",
             "choices": [("off", "仅本地菜谱库（默认 · 零配置 · 不联网）"),
                         ("openai", "OpenAI 兼容 API（云端，需要 Key）"),
                         ("ollama", "本地 Ollama（需要局域网内有 Ollama）")]},
            {"key": "openai_base_url", "label": "Base URL", "type": "text",
             "placeholder": "https://api.deepseek.com/v1",
             "hint": "DeepSeek / 通义 / Kimi / 智谱 / 硅基流动都填各自的 /v1 地址",
             "depends_on": {"llm_mode": "openai"}},
            {"key": "openai_api_key", "label": "API Key", "type": "password",
             "depends_on": {"llm_mode": "openai"}},
            {"key": "openai_model", "label": "模型名", "type": "text", "placeholder": "deepseek-chat",
             "depends_on": {"llm_mode": "openai"}},
            {"key": "ollama_base_url", "label": "Ollama 地址", "type": "text",
             "placeholder": "http://host.docker.internal:11434", "depends_on": {"llm_mode": "ollama"}},
            {"key": "ollama_model", "label": "Ollama 模型", "type": "text", "placeholder": "qwen2.5:7b",
             "depends_on": {"llm_mode": "ollama"}},
            {"key": "llm_temperature", "label": "随机性 temperature", "type": "float", "min": 0, "max": 2, "step": 0.05},
            {"key": "llm_timeout", "label": "超时（秒）", "type": "number", "min": 10, "max": 900},
            {"key": "llm_max_repair", "label": "校验失败重试次数", "type": "number", "min": 0, "max": 5},
        ],
    },
    {
        "group": "校验规则",
        "icon": "✅",
        "hint": "LLM 出的菜单会先过这几道闸，不合格就打回重生成；重试耗尽则用本地菜库兜底。",
        "fields": [
            {"key": "repeat_window_days", "label": "不重复窗口（天）", "type": "number", "min": 0, "max": 60},
            {"key": "require_meat_and_veg", "label": "必须荤素搭配", "type": "bool"},
            {"key": "strict_season", "label": "严格时令（不建议反季食材）", "type": "bool"},
        ],
    },
    {
        "group": "定时推送",
        "icon": "⏰",
        "hint": "推送内容为当天的午餐 / 晚餐菜单 + 购物清单。时间按容器时区（默认 Asia/Shanghai）。",
        "fields": [
            {"key": "scheduler_enabled", "label": "启用定时任务", "type": "bool"},
            {"key": "lunch_push_time", "label": "午餐推送时间", "type": "time"},
            {"key": "dinner_push_time", "label": "晚餐推送时间", "type": "time"},
            {"key": "push_days_ahead", "label": "提前几天播报", "type": "number", "min": 0, "max": 7,
             "hint": "0 = 当天；1 = 提前一天播报明天的菜，方便早上买菜"},
            {"key": "push_title_prefix", "label": "推送标题前缀", "type": "text"},
            {"key": "push_with_steps", "label": "推送里带简单做法", "type": "bool",
             "hint": "打开后每条推送末尾会附「👩‍🍳 简单做法」，老人照着就能做"},
        ],
    },
    {
        "group": "推送通道",
        "icon": "📮",
        "hint": "可多选。老人手机推荐「企业微信机器人」：免费、无审核、建个群拉进去就行。",
        "fields": [
            {"key": "push_channels", "label": "启用通道", "type": "checkboxes",
             "choices": [("wecom", "企业微信机器人"), ("serverchan", "Server 酱"),
                         ("pushplus", "PushPlus"), ("wxpusher", "WxPusher"),
                         ("feishu", "飞书机器人"), ("dingtalk", "钉钉机器人"),
                         ("bark", "Bark（iOS）"), ("custom", "自定义 Webhook")]},
            {"key": "wecom_webhook", "label": "企业微信 Webhook", "type": "password",
             "placeholder": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…"},
            {"key": "serverchan_key", "label": "Server 酱 SendKey", "type": "password",
             "placeholder": "SCT…"},
            {"key": "pushplus_token", "label": "PushPlus Token", "type": "password"},
            {"key": "pushplus_topic", "label": "PushPlus 群组编码（选填）", "type": "text"},
            {"key": "wxpusher_app_token", "label": "WxPusher AppToken", "type": "password",
             "placeholder": "AT_…"},
            {"key": "wxpusher_uid", "label": "WxPusher UID", "type": "text",
             "placeholder": "UID_…（多个用逗号分隔）"},
            {"key": "feishu_webhook", "label": "飞书 Webhook", "type": "password"},
            {"key": "dingtalk_webhook", "label": "钉钉 Webhook", "type": "password"},
            {"key": "dingtalk_secret", "label": "钉钉加签密钥（选填）", "type": "password"},
            {"key": "bark_url", "label": "Bark 推送地址", "type": "password",
             "placeholder": "https://api.day.app/你的Key"},
            {"key": "custom_webhook", "label": "自定义 Webhook（POST JSON）", "type": "text"},
        ],
    },
    {
        "group": "访问控制",
        "icon": "🔓",
        "hint": "家里局域网自用建议保持「免登录」，打开网页就能用，不用记账号密码。"
                "如果这台机器会被公网访问（端口映射 / 内网穿透），请务必改成「需要账号密码」。",
        "fields": [
            {"key": "auth_mode", "label": "访问方式", "type": "select",
             "choices": [("none", "免登录（打开即用 · 推荐家里局域网）"),
                         ("password", "需要账号密码（暴露到公网时必须选）")],
             "hint": "免登录 = 访问该地址的任何人都是管理员；请只在能信任的网络里这样用"},
        ],
    },
]


def field_map() -> dict[str, dict[str, Any]]:
    """key -> field 定义。"""
    return {f["key"]: f for group in SETTINGS_SCHEMA for f in group["fields"]}


# --------------------------------------------------------------------------------------
# 读写
# --------------------------------------------------------------------------------------
def load_config(db: Session) -> AppConfig:
    rows = db.execute(select(Setting)).scalars().all()
    stored: dict[str, Any] = {}
    for row in rows:
        try:
            stored[row.key] = json.loads(row.value)
        except (TypeError, json.JSONDecodeError):
            continue
    known = set(AppConfig.model_fields)
    payload = {k: v for k, v in stored.items() if k in known}
    return AppConfig(**payload)


def save_config(db: Session, config: AppConfig) -> AppConfig:
    data = config.model_dump()
    existing = {row.key: row for row in db.execute(select(Setting)).scalars().all()}
    for key, value in data.items():
        blob = json.dumps(value, ensure_ascii=False)
        if key in existing:
            existing[key].value = blob
        else:
            db.add(Setting(key=key, value=blob))
    db.commit()
    return config


def update_config(db: Session, updates: dict[str, Any]) -> AppConfig:
    config = load_config(db)
    known = set(AppConfig.model_fields)
    merged = config.model_dump()
    merged.update({k: v for k, v in updates.items() if k in known})
    return save_config(db, AppConfig(**merged))
