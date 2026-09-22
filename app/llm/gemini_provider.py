"""Google Gemini 原生通道（generativelanguage.googleapis.com 或反代）。

用 generateContent 而不是 OpenAI 兼容层，好处是能用 responseMimeType 强制 JSON，
配合本项目的 JSON 校验链路更稳。
"""
from __future__ import annotations

import time

import httpx

from .base import BaseLLM, LLMError, LLMResult


class GeminiLLM(BaseLLM):
    provider = "gemini"

    @property
    def model(self) -> str:
        return self.config.gemini_model

    @property
    def auth_headers(self) -> dict[str, str]:
        # 官方用 x-goog-api-key；也兼容 query 参数式反代（key 走 URL）
        key = (self.config.gemini_api_key or "").strip()
        return {"x-goog-api-key": key} if key else {}

    def _endpoint(self) -> str:
        base = (self.config.gemini_base_url or "").strip().rstrip("/")
        if not base:
            raise LLMError("未配置 Gemini Base URL")
        model = (self.model or "").strip()
        if not model:
            raise LLMError("未配置 Gemini 模型名（可点「列出可用模型」选一个）")
        if ":generateContent" in base:
            return base
        # 允许用户直接填到 /v1beta
        if base.endswith("/v1beta") or base.endswith("/v1"):
            return f"{base}/models/{model}:generateContent"
        return f"{base}/v1beta/models/{model}:generateContent"

    @staticmethod
    def _to_contents(messages: list[dict[str, str]]) -> tuple[dict, list[dict]]:
        """Gemini 把 system 放 systemInstruction，其余进 contents（role 只有 user/model）。"""
        system_text = ""
        contents: list[dict] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                system_text = f"{system_text}\n\n{content}".strip()
                continue
            contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": content}]})
        system_instruction = {"parts": [{"text": system_text}]} if system_text else {}
        return system_instruction, contents

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        system_instruction, contents = self._to_contents(messages)
        generation_config: dict = {
            "temperature": self.config.llm_temperature,
            "maxOutputTokens": self.config.llm_max_tokens,
        }
        if json_mode and self.config.llm_json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: dict = {"contents": contents, "generationConfig": generation_config}
        if system_instruction:
            payload["systemInstruction"] = system_instruction

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

        if isinstance(data.get("error"), dict):
            raise LLMError(f"接口报错：{data['error'].get('message', '')}")

        try:
            candidates = data["candidates"]
            parts = candidates[0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            # 被安全策略拦掉时 candidates 会是空的，提示得具体一点
            feedback = (data.get("promptFeedback") or {}).get("blockReason")
            if feedback:
                raise LLMError(f"被 Gemini 安全策略拦截：{feedback}") from exc
            raise LLMError(f"返回结构异常：{str(data)[:300]}") from exc

        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        usage = data.get("usageMetadata") or {}
        return LLMResult(
            text=text,
            provider=self.provider,
            model=self.model,
            elapsed_ms=elapsed,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            raw={"finish_reason": (candidates[0].get("finishReason") if candidates else "") or ""},
        )

    async def list_models(self) -> list[str]:
        base = (self.config.gemini_base_url or "").strip().rstrip("/")
        if not base:
            return []
        url = f"{base}/v1beta/models" if not base.endswith(("/v1beta", "/v1")) else f"{base}/models"
        headers = {k: v for k, v in self.base_headers.items() if k != "Content-Type"}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code >= 400:
                    return []
                data = resp.json()
        except Exception:
            return []
        out = []
        for item in data.get("models") or []:
            name = item.get("name") if isinstance(item, dict) else None
            if name:
                out.append(str(name).removeprefix("models/"))
        return sorted(set(out))
