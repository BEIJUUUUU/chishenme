"""钉钉群机器人（支持加签）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class DingTalkNotifier(BaseNotifier):
    key = "dingtalk"
    label = "钉钉机器人"
    config_fields = ("dingtalk_webhook",)
    doc = "钉钉群 → 智能群助手 → 添加机器人 → 自定义 → 复制 Webhook；若开启加签请填密钥"
    max_length = 20000

    def _sign(self, url: str, secret: str) -> str:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest).decode())
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}timestamp={timestamp}&sign={sign}"

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        url = self.value(config, "dingtalk_webhook")
        if not url:
            return self.fail("未配置 Webhook")

        secret = self.value(config, "dingtalk_secret")
        if secret:
            url = self._sign(url, secret)

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title[:60], "text": self.clip(f"## {title}\n\n{markdown}")},
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")

        if data.get("errcode") == 0:
            return self.ok("已推送到钉钉群")
        return self.fail(f"errcode={data.get('errcode')} {data.get('errmsg', '')}")
