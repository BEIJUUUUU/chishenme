"""本地 Ollama 通道。适合零成本离线跑 qwen2.5 等中文模型。"""
from __future__ import annotations

import time

import httpx

from .base import BaseLLM, LLMError, LLMResult


class OllamaLLM(BaseLLM):
    provider = "ollama"

    @property
    def model(self) -> str:
        return self.config.ollama_model

    def _endpoint(self) -> str:
        base = (self.config.ollama_base_url or "").strip().rstrip("/")
        if not base:
            raise LLMError("未配置 Ollama 地址")
        if base.endswith("/api/chat"):
            return base
        return f"{base}/api/chat"

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.config.llm_temperature},
        }
        if json_mode and self.config.llm_json_mode:
            payload["format"] = "json"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.config.llm_timeout) as client:
                # 自定义头也带上：Ollama 挂在带鉴权的反代后面时用得上
                resp = await client.post(self._endpoint(), json=payload, headers=self.base_headers)
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama 请求超时（{self.config.llm_timeout}s），大模型首次加载较慢") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接 Ollama（{self._endpoint()}）：{exc}") from exc

        elapsed = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            if resp.status_code == 404:
                raise LLMError(f"模型 {self.model} 不存在，先执行：ollama pull {self.model}")
            self.handle_status(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(f"返回非 JSON：{resp.text[:300]}") from exc

        if data.get("error"):
            raise LLMError(str(data["error"]))

        text = (data.get("message") or {}).get("content", "")
        return LLMResult(
            text=text or "",
            provider=self.provider,
            model=data.get("model", self.model),
            elapsed_ms=elapsed,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
        )

    async def list_models(self) -> list[str]:
        base = (self.config.ollama_base_url or "").strip().rstrip("/")
        if base.endswith("/api/chat"):
            base = base[: -len("/api/chat")]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base}/api/tags")
                resp.raise_for_status()
                return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception:
            return []
