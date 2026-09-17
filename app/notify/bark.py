"""Bark（iOS）与通用自定义 Webhook。"""
from __future__ import annotations

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class BarkNotifier(BaseNotifier):
    key = "bark"
    label = "Bark（iOS）"
    config_fields = ("bark_url",)
    doc = "形如 https://api.day.app/你的Key"
    max_length = 3000

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        base = self.value(config, "bark_url").rstrip("/")
        if not base:
            return self.fail("未配置 Bark 地址")
        payload = {"title": title[:60], "body": self.clip(plain), "group": "吃什么"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(base, json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")
        if data.get("code") in (200, 0):
            return self.ok("已通过 Bark 推送")
        return self.fail(str(data)[:200])


class CustomWebhookNotifier(BaseNotifier):
    key = "custom"
    label = "自定义 Webhook"
    config_fields = ("custom_webhook",)
    doc = "向该地址 POST JSON：{title, markdown, plain}，可对接 HomeAssistant / Node-RED / n8n"
    max_length = 30000

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        url = self.value(config, "custom_webhook")
        if not url:
            return self.fail("未配置 Webhook")
        payload = {"title": title, "markdown": self.clip(markdown), "plain": self.clip(plain)}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        if resp.status_code < 400:
            return self.ok(f"HTTP {resp.status_code}")
        return self.fail(f"HTTP {resp.status_code}：{resp.text[:200]}")
