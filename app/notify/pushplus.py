"""PushPlus（pushplus.plus）。支持一对多群组推送。"""
from __future__ import annotations

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class PushPlusNotifier(BaseNotifier):
    key = "pushplus"
    label = "PushPlus"
    config_fields = ("pushplus_token",)
    doc = "在 pushplus.plus 微信登录后获取 token，可建群组一对多推送"
    max_length = 20000

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        token = self.value(config, "pushplus_token")
        if not token:
            return self.fail("未配置 Token")

        payload = {
            "token": token,
            "title": title[:100],
            "content": self.clip(markdown),
            "template": "markdown",
        }
        topic = self.value(config, "pushplus_topic")
        if topic:
            payload["topic"] = topic

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post("https://www.pushplus.plus/send", json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")

        if data.get("code") == 200:
            return self.ok("已通过 PushPlus 推送")
        return self.fail(f"code={data.get('code')} {data.get('msg', '')}")
