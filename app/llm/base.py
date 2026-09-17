"""LLM 提供方基类与公共数据结构。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..runtime_config import AppConfig


class LLMError(RuntimeError):
    """LLM 调用失败（网络、鉴权、限流、格式错误统一抛这个）。"""


@dataclass
class LLMResult:
    text: str
    provider: str = ""
    model: str = ""
    elapsed_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: dict = field(default_factory=dict)


class BaseLLM(ABC):
    provider: str = "base"

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def model(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        """执行一次对话补全。messages 为 OpenAI 风格 [{role, content}]。"""

    async def aclose(self) -> None:  # pragma: no cover - 默认无资源
        return None

    async def __aenter__(self) -> BaseLLM:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
