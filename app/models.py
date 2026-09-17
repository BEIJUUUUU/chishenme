"""数据模型。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now()


class Setting(Base):
    """运行期配置，key-value，value 为 JSON 字符串。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64), default="管理员")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Dish(Base):
    """本地菜谱库。LLM 生成的菜校验通过后也可回流入库。"""

    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    province: Mapped[str] = mapped_column(String(32), default="通用", index=True)
    category: Mapped[str] = mapped_column(String(16), default="荤菜", index=True)  # 荤菜/素菜/汤/凉菜/主食
    season: Mapped[str] = mapped_column(String(32), default="四季", index=True)

    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    spicy: Mapped[int] = mapped_column(Integer, default=0)  # 0-3

    #: 一句话做法要点（手机上只看这一句就够）
    howto: Mapped[str] = mapped_column(Text, default="")
    #: 三步做法，形如「①… ②… ③…」
    steps: Mapped[str] = mapped_column(Text, default="")

    source: Mapped[str] = mapped_column(String(16), default="local")  # local/llm/manual
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    popularity: Mapped[int] = mapped_column(Integer, default=0)  # 被采用次数，越高越容易再被选中
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Plan(Base):
    """某天某一餐的菜单。"""

    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("plan_date", "meal", name="uq_plan_date_meal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(String(8), index=True)  # 午餐 / 晚餐

    dishes: Mapped[list] = mapped_column(JSON, default=list)   # [{name, category, ingredients, note, steps}]
    soup: Mapped[str] = mapped_column(String(64), default="")
    staple: Mapped[str] = mapped_column(String(32), default="米饭")
    shopping: Mapped[list] = mapped_column(JSON, default=list)  # [{name, category, count}]
    #: 做法快照 {菜名: {howto, steps}} —— 生成时定下来，之后改菜谱库不会影响历史菜单
    recipes: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")       # LLM 给出的搭配理由

    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok/fallback/failed
    source: Mapped[str] = mapped_column(String(16), default="llm")  # llm/local
    issues: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(64), default="")

    pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    logs: Mapped[list[PushLog]] = relationship(back_populates="plan", cascade="all, delete-orphan")

    @property
    def dish_names(self) -> list[str]:
        return [d.get("name", "") for d in (self.dishes or []) if d.get("name")]

    @property
    def all_dish_names(self) -> list[str]:
        names = self.dish_names
        if self.soup:
            names.append(self.soup)
        return names


class PushLog(Base):
    __tablename__ = "push_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str] = mapped_column(String(64), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    plan: Mapped[Plan | None] = relationship(back_populates="logs")


class GenerationLog(Base):
    """记录每次 LLM 调用，用于排查幻觉与费用。"""

    __tablename__ = "generation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(String(8), default="")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
