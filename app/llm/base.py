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


def parse_extra_headers(raw: str) -> dict[str, str]:
    """把「每行一条 Key: Value」解析成请求头字典。

    给需要特殊鉴权头的反代/网关用（比如要求 X-Api-Key 或 X-Token 的场景）。
    非法行直接跳过，不让用户因为多打一个空行就整条链路失败。
    """
    headers: dict[str, str] = {}
    for line in (raw or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if ":" not in text:
            continue
        key, _, value = text.partition(":")
        key = key.strip()
        value = value.strip()
        if key:
            headers[key] = value
    return headers


def join_url(base: str, path: str) -> str:
    """把 base 与路径拼起来，避免出现 // 或漏掉 /。

    用户填 base 的习惯差别很大：有人填到 /v1，有人直接填完整 endpoint，
    所以各 provider 用这个函数统一收口。
    """
    base = (base or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith(path):
        return base
    return f"{base}/{path.lstrip('/')}"


class BaseLLM(ABC):
    provider: str = "base"

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def model(self) -> str:
        raise NotImplementedError

    @property
    def auth_headers(self) -> dict[str, str]:
        """通道自带的鉴权头，子类覆盖。"""
        return {}

    @property
    def base_headers(self) -> dict[str, str]:
        """鉴权头 + 用户自定义头（自定义头放在后面，方便覆盖默认值）。"""
        headers = {"Content-Type": "application/json", **self.auth_headers}
        headers.update(parse_extra_headers(self.config.llm_extra_headers))
        return headers

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> LLMResult:
        """执行一次对话补全。messages 为 OpenAI 风格 [{role, content}]。"""

    async def list_models(self) -> list[str]:
        """列出可用模型名，供 WebUI 下拉选择。不支持的通道返回空列表。"""
        return []

    def clip(self, text: str, limit: int = 400) -> str:
        return text[:limit]

    def handle_status(self, status: int, body: str) -> None:
        """统一的 HTTP 错误转 LLMError。"""
        detail = self.clip(body)
        if status in (401, 403):
            raise LLMError(f"鉴权失败（{status}），检查 API Key / 令牌：{detail}")
        if status == 404:
            raise LLMError(f"接口不存在（404），检查 Base URL 是否填错：{detail}")
        if status == 429:
            raise LLMError(f"限流（429）：{detail}")
        raise LLMError(f"HTTP {status}：{detail}")

    async def aclose(self) -> None:  # pragma: no cover - 默认无资源
        return None

    async def __aenter__(self) -> BaseLLM:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
