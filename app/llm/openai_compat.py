"""OpenAI 兼容通道：DeepSeek / 通义千问 / Kimi / 智谱 / 硅基流动 / vLLM / one-api …"""
from __future__ import annotations

import time

import httpx

from .base import BaseLLM, LLMError, LLMResult


class OpenAICompatLLM(BaseLLM):
    provider = "openai"

    @property
    def model(self) -> str:
        return self.config.openai_model

    def _endpoint(self) -> str:
        base = (self.config.openai_base_url or "").strip().rstrip("/")
        if not base:
            raise LLMError("未配置 OpenAI 兼容 Base URL")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        api_key = (self.config.openai_api_key or "").strip()
        if not api_key:
            raise LLMError("未配置 API Key")

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.llm_temperature,
            "stream": False,
        }
        if json_mode and self.config.llm_json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.config.llm_timeout) as client:
                resp = await client.post(self._endpoint(), json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMError(f"请求超时（{self.config.llm_timeout}s）") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"网络错误：{exc}") from exc

        elapsed = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            detail = resp.text[:400]
            if resp.status_code in (401, 403):
                raise LLMError(f"鉴权失败（{resp.status_code}），检查 API Key：{detail}")
            if resp.status_code == 429:
                raise LLMError(f"限流（429）：{detail}")
            raise LLMError(f"HTTP {resp.status_code}：{detail}")

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
