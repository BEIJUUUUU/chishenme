"""通道注册表与统一发送入口。"""
from __future__ import annotations

import asyncio

from ..runtime_config import AppConfig
from .bark import BarkNotifier, CustomWebhookNotifier
from .base import BaseNotifier, NotifyResult
from .dingtalk import DingTalkNotifier
from .feishu import FeishuNotifier
from .pushplus import PushPlusNotifier
from .serverchan import ServerChanNotifier
from .wecom import WeComNotifier
from .wxpusher import WxPusherNotifier

NOTIFIERS: dict[str, BaseNotifier] = {
    n.key: n
    for n in (
        WeComNotifier(),
        ServerChanNotifier(),
        PushPlusNotifier(),
        WxPusherNotifier(),
        FeishuNotifier(),
        DingTalkNotifier(),
        BarkNotifier(),
        CustomWebhookNotifier(),
    )
}


def channel_choices() -> list[tuple[str, str]]:
    return [(key, n.label) for key, n in NOTIFIERS.items()]


def get_notifier(channel: str) -> BaseNotifier | None:
    return NOTIFIERS.get(channel)


async def send_to_channel(channel: str, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
    notifier = NOTIFIERS.get(channel)
    if notifier is None:
        return NotifyResult(channel=channel, ok=False, message=f"未知通道：{channel}")
    if not notifier.configured(config):
        return NotifyResult(channel=channel, ok=False, message="未配置")
    try:
        return await notifier.send(title, markdown, plain, config)
    except Exception as exc:  # pragma: no cover - 兜底，绝不让推送炸掉调度器
        return NotifyResult(channel=channel, ok=False, message=f"异常：{exc}")


async def send_all(
    config: AppConfig,
    title: str,
    markdown: str,
    plain: str,
    channels: list[str] | None = None,
) -> list[NotifyResult]:
    targets = [c for c in (channels if channels is not None else config.push_channels) if c in NOTIFIERS]
    if not targets:
        return []
    results = await asyncio.gather(
        *(send_to_channel(c, title, markdown, plain, config) for c in targets)
    )
    return list(results)
