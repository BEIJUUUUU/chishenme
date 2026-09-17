"""应用级配置（环境变量 / .env），前缀 CSM_。

与「用户可编辑的家庭配置」区分开：
- 这里放的是启动参数（端口、密钥、数据目录）
- 家庭画像 / LLM / 推送等运行期可变配置存在数据库 settings 表里，见 app/settings_schema.py
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CSM_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "吃什么？"
    version: str = "0.1.0"

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    secret_key: str = "change-me-to-a-random-string"
    session_cookie: str = "csm_session"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 天免登录

    admin_user: str = "admin"
    admin_password: str = "admin123"

    data_dir: Path = BASE_DIR / "runtime"
    timezone: str = "Asia/Shanghai"

    auto_update_library: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "chishenme.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.log_dir, self.export_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
