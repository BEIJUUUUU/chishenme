"""Server 酱（sct.ftqq.com）。免费额度有限，适合个人微信。
"""
from __future__ import annotations

import httpx

from ..runtime_config import AppConfig
from .base import BaseNotifier, NotifyResult


class ServerChanNotifier(BaseNotifier):
    key = "serverchan"
    label = "Server 酱"
    config_fields = ("serverchan_key",)
    doc = "在 sct.ftqq.com 获取 SendKey（SCT 开头）"
    max_length = 30000

    def _endpoint(self, key: str) -> str:
        if key.startswith("sctp"):
            # 新版 Turbo 前缀带协议版本号
            number = key[4:].split("t")[0] if "t" in key[4:] else "1"
            return f"https://{number}.push.ft07.com/send/{key}.send"
        return f"https://sctapi.ftqq.com/{key}.send"

    async def send(self, title: str, markdown: str, plain: str, config: AppConfig) -> NotifyResult:
        key = self.value(config, "serverchan_key")
        if not key:
            return self.fail("未配置 SendKey")

        payload = {"title": title[:32], "desp": self.clip(plain)}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(self._endpoint(key), data=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            return self.fail(f"网络错误：{exc}")
        except ValueError:
            return self.fail(f"返回非 JSON：{resp.text[:200]}")

        if data.get("code") == 0:
            return self.ok("已通过 Server 酱推送")

        # 带 markdown 再试一次
        try:
            payload["desp"] = self.clip(f"# {title}\n\n{markdown}")
            payload["tags"] = "吃什么"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(self._endpoint(key), data=payload)
                data = resp.json()
            if data.get("code") == 0:
                return self.ok("已通过 Server 酱推送")
        except Exception:  # pragma: no cover
            pass

        return self.fail(f"code={data.get('code')} {data.get('message') or data.get('info', '')}")
