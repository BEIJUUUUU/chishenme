"""LLM 通道抽象层。

统一接口：`await llm.chat(messages, json_mode=...) -> LLMResult`
- openai  : 任何 OpenAI 兼容的 /chat/completions（DeepSeek、通义、Kimi、智谱、硅基流动、vLLM…）
- ollama  : 本地 Ollama /api/chat

新增通道只需实现 BaseLLM 并在 factory 里注册。
"""
from .base import BaseLLM, LLMError, LLMResult
from .factory import build_llm, test_connection

__all__ = ["BaseLLM", "LLMError", "LLMResult", "build_llm", "test_connection"]
