"""飞书群机器人。"""
from __future__ import annotations

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class FeishuNotifier(BaseNotifier):
    key = "feishu"
    label = "飞书机器人"
    config_fields = ("feishu_webhook",)
    doc = "飞书群 → 设置 → 群机器人 → 自定义机器人 → 复制 Webhook"
    max_length = 30000

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        url = self.value(config, "feishu_webhook")
        if not url:
            return self.fail("未配置 Webhook")

        payload = {"msg_type": "text", "content": {"text": self.clip(f"{title}\n\n{plain}")}}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")

        code = data.get("code", data.get("StatusCode", 0))
        if code == 0:
            return self.ok("已推送到飞书群")
        return self.fail(f"code={code} {data.get('msg', data.get('StatusMessage', ''))}")
