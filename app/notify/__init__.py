"""推送通道抽象层。

新增一个通道 = 写一个 BaseNotifier 子类 + 在 registry 里注册。
"""
from .base import BaseNotifier, NotifyResult
from .registry import NOTIFIERS, channel_choices, send_all, send_to_channel

__all__ = [
    "NOTIFIERS",
    "BaseNotifier",
    "NotifyResult",
    "channel_choices",
    "send_all",
    "send_to_channel",
]
