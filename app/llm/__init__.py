"""LLM 通道抽象层。

统一接口：`await llm.chat(messages, json_mode=...) -> LLMResult`
- openai    : 任何 OpenAI 兼容的 /chat/completions
              （DeepSeek、通义、Kimi、智谱、硅基流动、vLLM、LM Studio、llama.cpp、
               LocalAI、one-api/new-api 网关、大多数反代）
- anthropic : Anthropic 兼容的 /v1/messages
              （官方 Claude，以及 cliproxy / claude-code-proxy 这类 CLI 反代）
- ollama    : 本地 Ollama /api/chat
- gemini    : Google Gemini 原生 generateContent

新增通道只需实现 BaseLLM 并在 factory 里注册。
"""
from .base import BaseLLM, LLMError, LLMResult, join_url, parse_extra_headers
from .factory import (
    PROVIDER_LABELS,
    build_llm,
    describe_missing,
    is_configured,
    list_models,
    looks_local,
    test_connection,
)

__all__ = [
    "PROVIDER_LABELS",
    "BaseLLM",
    "LLMError",
    "LLMResult",
    "build_llm",
    "describe_missing",
    "is_configured",
    "join_url",
    "list_models",
    "looks_local",
    "parse_extra_headers",
    "test_connection",
]
