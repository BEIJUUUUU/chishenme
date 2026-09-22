"""OpenAI 兼容通道。

一个实现覆盖一大片：
- 云端：DeepSeek / 通义千问 / Kimi / 智谱 / 硅基流动 / OpenAI 自己
- 本地：LM Studio / vLLM / llama.cpp / LocalAI / text-generation-webui
- 网关与反代：one-api / new-api / 各种中转站（通常同时提供 OpenAI 与 Anthropic 两种入口）
"""
from __future__ import annotations

import time

import httpx

from .base import BaseLLM, LLMError, LLMResult, join_url


class OpenAICompatLLM(BaseLLM):
    provider = "openai"

    @property
    def model(self) -> str:
        return self.config.openai_model

    @property
    def auth_headers(self) -> dict[str, str]:
        # 本地推理服务（LM Studio / llama.cpp）通常不校验 Key，不填就不发这个头
        key = (self.config.openai_api_key or "").strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _endpoint(self) -> str:
        base = (self.config.openai_base_url or "").strip().rstrip("/")
        if not base:
            raise LLMError("未配置 OpenAI 兼容 Base URL")
        if base.endswith("/chat/completions"):
            return base
        # 很多人只填到域名或 /v1，这里统一补全
        return join_url(base, "chat/completions")

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.llm_temperature,
            "stream": False,
        }
        if json_mode and self.config.llm_json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.config.llm_timeout) as client:
                resp = await client.post(self._endpoint(), json=payload, headers=self.base_headers)
        except httpx.TimeoutException as exc:
            raise LLMError(f"请求超时（{self.config.llm_timeout}s）") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"网络错误：{exc}") from exc

        elapsed = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            self.handle_status(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(f"返回非 JSON：{resp.text[:300]}") from exc

        if data.get("error"):
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise LLMError(f"接口报错：{msg}")

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"返回结构异常：{str(data)[:300]}") from exc

        usage = data.get("usage") or {}
        return LLMResult(
            text=text or "",
            provider=self.provider,
            model=data.get("model", self.model),
            elapsed_ms=elapsed,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            raw={"id": data.get("id", "")},
        )

    async def list_models(self) -> list[str]:
        """GET {base}/models —— OpenAI 兼容约定，绝大多数服务与反代都实现。"""
        url = join_url(self.config.openai_base_url, "models")
        if not url:
            return []
        headers = {k: v for k, v in self.base_headers.items() if k != "Content-Type"}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code >= 400:
                    return []
                data = resp.json()
        except Exception:
            return []

        items = data.get("data") if isinstance(data, dict) else None
        if items is None and isinstance(data, dict):
            items = data.get("models")
        out: list[str] = []
        for item in items or []:
            if isinstance(item, dict):
                name = item.get("id") or item.get("name") or item.get("model")
            else:
                name = str(item)
            if name:
                out.append(str(name))
        return sorted(set(out))
