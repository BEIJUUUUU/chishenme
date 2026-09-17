"""WxPusher（wxpusher.zjiecode.com）。支持 UID 精准推送，适合给家人单独发。"""
from __future__ import annotations

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class WxPusherNotifier(BaseNotifier):
    key = "wxpusher"
    label = "WxPusher"
    config_fields = ("wxpusher_app_token", "wxpusher_uid")
    doc = "wxpusher.zjiecode.com 创建应用拿 AppToken，关注后拿 UID（多个用逗号分隔）"
    max_length = 20000

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        app_token = self.value(config, "wxpusher_app_token")
        if not app_token:
            return self.fail("未配置 AppToken")

        uids = [u.strip() for u in self.value(config, "wxpusher_uid").replace("，", ",").split(",") if u.strip()]
        if not uids:
            return self.fail("未配置 UID")

        payload = {
            "appToken": app_token,
            "content": self.clip(markdown),
            "summary": title[:99],
            "contentType": 3,  # 3 = markdown
            "uids": uids,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post("https://wxpusher.zjiecode.com/api/send/message", json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")

        if data.get("code") == 1000:
            return self.ok(f"已推送给 {len(uids)} 个 UID")
        return self.fail(f"code={data.get('code')} {data.get('msg', '')}")
