"""推送通道基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..runtime_config import AppConfig


@dataclass
class NotifyResult:
    channel: str
    ok: bool
    message: str = ""
    target: str = ""

    def as_dict(self) -> dict:
        return {"channel": self.channel, "ok": self.ok, "message": self.message, "target": self.target}


class BaseNotifier(ABC):
    key: str = "base"
    label: str = "基类"
    #: 该通道读取的 AppConfig 字段名（第一个视为「主配置项」，用于判断是否已配置）
    config_fields: tuple[str, ...] = ()
    doc: str = ""
    max_length: int = 4000

    @abstractmethod
    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        """发送一条消息。实现里不要抛异常，失败请返回 ok=False。"""

    def value(self, config: AppConfig, field: str) -> str:
        return str(getattr(config, field, "") or "").strip()

    def configured(self, config: AppConfig) -> bool:
        if not self.config_fields:
            return True
        return bool(self.value(config, self.config_fields[0]))

    def mask(self, config: AppConfig) -> str:
        if not self.config_fields:
            return ""
        raw = self.value(config, self.config_fields[0])
        if len(raw) <= 12:
            return "已配置" if raw else "未配置"
        return f"{raw[:8]}…{raw[-4:]}"

    def fail(self, message: str, target: str = "") -> NotifyResult:
        return NotifyResult(channel=self.key, ok=False, message=message, target=target)

    def ok(self, message: str = "发送成功", target: str = "") -> NotifyResult:
        return NotifyResult(channel=self.key, ok=True, message=message, target=target)

    def clip(self, text: str) -> str:
        if len(text) <= self.max_length:
            return text
        return text[: self.max_length - 20] + "\n…（内容过长已截断）"
