"""Anthropic 兼容通道（/v1/messages）。

覆盖两类场景：
1. 官方 Claude API（https://api.anthropic.com）
2. **cliproxy / claude-code-proxy / 各种把 CLI 订阅转成 API 的反代** ——
   它们通常监听在局域网某台机器上（如 http://192.168.1.10:8317），
   接口形状与官方一致，但往往不校验 Key（留空也能用）。

实现上做了一件防御性的事：如果对方无视 stream=false 直接回 SSE 流，
这里会把流里的增量拼回完整文本，而不是直接报「返回非 JSON」。
"""
from __future__ import annotations

import json
import time

import httpx

from .base import BaseLLM, LLMError, LLMResult, join_url


def parse_sse_text(body: str) -> str:
    """把 Anthropic 风格的 SSE 流拼成完整文本（兼容 message_delta / content_block_delta）。"""
    chunks: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        delta = event.get("delta") or {}
        if isinstance(delta, dict) and isinstance(delta.get("text"), str):
            chunks.append(delta["text"])
            continue
        content_block = event.get("content_block") or {}
        if isinstance(content_block, dict) and isinstance(content_block.get("text"), str):
            chunks.append(content_block["text"])
    return "".join(chunks)


class AnthropicCompatLLM(BaseLLM):
    provider = "anthropic"

    @property
    def model(self) -> str:
        return self.config.anthropic_model

    @property
    def auth_headers(self) -> dict[str, str]:
        # 官方 API 认 x-api-key；反代一般不校验，没填就不发
        key = (self.config.anthropic_api_key or "").strip()
        version = (self.config.anthropic_version or "2023-06-01").strip() or "2023-06-01"
        headers = {"anthropic-version": version}
        if key:
            headers["x-api-key"] = key
        return headers

    def _endpoint(self) -> str:
        base = (self.config.anthropic_base_url or "").strip().rstrip("/")
        if not base:
            raise LLMError("未配置 Anthropic 兼容 Base URL")
        if base.endswith("/v1/messages"):
            return base
        if base.endswith("/v1"):
            return f"{base}/messages"
        return join_url(base, "v1/messages")

    @staticmethod
    def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Anthropic 把 system 单独放在顶层字段，不在 messages 里。"""
        system_parts: list[str] = []
        chat: list[dict[str, str]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                chat.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        if not chat:  # 兜底：Anthropic 要求 messages 非空
            chat = [{"role": "user", "content": "继续"}]
        return "\n\n".join(system_parts), chat

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        system, chat = self._split_system(messages)
        payload: dict = {
            "model": self.model,
            "max_tokens": self.config.llm_max_tokens,
            "temperature": self.config.llm_temperature,
            "messages": chat,
            "stream": False,
        }
        if system:
            payload["system"] = system
        # 注：Messages API 没有 response_format，JSON 约束靠提示词 + 本地校验兜底

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

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            # 反代无视 stream=false 的情况：把流拼回来
            text = parse_sse_text(resp.text)
            if not text:
                raise LLMError(f"流式返回里没解析到文本：{resp.text[:300]}")
            return LLMResult(text=text, provider=self.provider, model=self.model, elapsed_ms=elapsed)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(f"返回非 JSON：{resp.text[:300]}") from exc

        if isinstance(data.get("error"), dict):
            raise LLMError(f"接口报错：{data['error'].get('message', '')}")

        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise LLMError(f"返回结构异常：{str(data)[:300]}")
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type", "text") == "text"
        )

        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            provider=self.provider,
            model=data.get("model", self.model),
            elapsed_ms=elapsed,
            prompt_tokens=int(usage.get("input_tokens") or 0),
            completion_tokens=int(usage.get("output_tokens") or 0),
            raw={"id": data.get("id", ""), "stop_reason": data.get("stop_reason", "")},
        )

    async def list_models(self) -> list[str]:
        base = (self.config.anthropic_base_url or "").strip().rstrip("/")
        url = join_url(base, "v1/models")
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
        out = []
        for item in items or []:
            name = item.get("id") if isinstance(item, dict) else str(item)
            if name:
                out.append(str(name))
        return sorted(set(out))
