"""企业微信群机器人。老人手机最省事的通道：建个群 → 添加群机器人 → 复制 Webhook。

优点：免费、无需审核、无需公众号、成员进群即可收到。
"""
from __future__ import annotations

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class WeComNotifier(BaseNotifier):
    key = "wecom"
    label = "企业微信机器人"
    config_fields = ("wecom_webhook",)
    doc = "企业微信群 → 添加群机器人 → 复制 Webhook 地址"
    max_length = 4000

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        url = self.value(config, "wecom_webhook")
        if not url:
            return self.fail("未配置 Webhook")

        content = self.clip(f"## {title}\n{markdown}")
        payload = {"msgtype": "markdown", "markdown": {"content": content}}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")

        if data.get("errcode") == 0:
            return self.ok("已推送到企业微信群")
        return self.fail(f"errcode={data.get('errcode')} {data.get('errmsg', '')}")
