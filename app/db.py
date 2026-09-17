"""SQLite + SQLAlchemy 2.0 会话管理。"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, _record) -> None:
    """WAL 提升并发读写表现，外键约束打开。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """后台任务（调度器 / CLI）用的事务上下文。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(bind=engine)
    ensure_schema()


#: 老版本数据库缺的列 —— 用 SQLite 原生 ALTER TABLE 补上，
#: 这样从旧版本升级上来的人不用删库重来。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "dishes": {
        "howto": "TEXT DEFAULT ''",
        "steps": "TEXT DEFAULT ''",
    },
    "plans": {
        "recipes": "TEXT DEFAULT '{}'",
    },
}


def ensure_schema(bind=None) -> None:
    """轻量迁移：给已存在的表补上后来新增的列。

    bind 为空时用全局 engine；测试里可以传一个临时 engine 验证升级路径。
    """
    target = bind if bind is not None else engine
    with target.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not existing:
                continue  # 表还不存在，create_all 已经建好了完整结构
            for name, ddl in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
