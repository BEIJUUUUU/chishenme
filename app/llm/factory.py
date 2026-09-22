"""通道工厂、可用性判断、连通性自检与模型列表。"""
from __future__ import annotations

import re

from ..runtime_config import AppConfig
from .anthropic_compat import AnthropicCompatLLM
from .base import BaseLLM, LLMError
from .gemini_provider import GeminiLLM
from .ollama_provider import OllamaLLM
from .openai_compat import OpenAICompatLLM

PROVIDERS: dict[str, type[BaseLLM]] = {
    "openai": OpenAICompatLLM,
    "anthropic": AnthropicCompatLLM,
    "ollama": OllamaLLM,
    "gemini": GeminiLLM,
}

PROVIDER_LABELS = {
    "off": "仅本地菜谱库",
    "openai": "OpenAI 兼容",
    "anthropic": "Anthropic 兼容（Claude / cliproxy 反代）",
    "ollama": "本地 Ollama",
    "gemini": "Google Gemini",
}

_LOCAL_HOST_RE = re.compile(
    r"(localhost|127\.0\.0\.1|0\.0\.0\.0|host\.docker\.internal|\[::1\])",
    re.IGNORECASE,
)
_PRIVATE_IP_RE = re.compile(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)")


def looks_local(url: str) -> bool:
    """判断地址是不是局域网/本机 —— 本地推理服务通常不需要 API Key。"""
    text = (url or "").strip().lower()
    if not text:
        return False
    host = text.split("://", 1)[-1].split("/", 1)[0].split("@")[-1].split(":")[0]
    return bool(_LOCAL_HOST_RE.search(host) or _PRIVATE_IP_RE.match(host))


def is_configured(config: AppConfig) -> bool:
    """是否真的能调到大模型。

    这是「零配置可用」的关键：没配置就走本地菜谱库，不再白等重试、不再刷错误日志。

    注意 openai / anthropic 两条通道：Base URL 指向本机或局域网时允许不填 Key
    （LM Studio、llama.cpp、cliproxy 这类反代本来就不校验），
    指向公网服务则必须有 Key —— 否则用户只会收获一串 401。
    """
    mode = config.llm_mode

    if mode == "openai":
        base = (config.openai_base_url or "").strip()
        if not base:
            return False
        return bool((config.openai_api_key or "").strip()) or looks_local(base)

    if mode == "anthropic":
        base = (config.anthropic_base_url or "").strip()
        if not base:
            return False
        if not (config.anthropic_model or "").strip():
            return False  # 模型名必填，反代不会替你猜
        return bool((config.anthropic_api_key or "").strip()) or looks_local(base)

    if mode == "ollama":
        return bool((config.ollama_base_url or "").strip())

    if mode == "gemini":
        return bool((config.gemini_api_key or "").strip()) and bool((config.gemini_model or "").strip())

    return False


def describe_missing(config: AppConfig) -> str:
    """配置不完整时，告诉用户到底缺哪一项。"""
    mode = config.llm_mode
    if mode == "off":
        return (
            "当前是「仅本地菜谱库」模式：不调用大模型，用内置家常菜按时令与忌口搭配，完全离线可用。"
            "想让 AI 自由配菜，把通道切成 OpenAI 兼容 / Anthropic 兼容 / Ollama / Gemini 之一。"
        )
    if mode == "openai":
        if not (config.openai_base_url or "").strip():
            return "❌ 还没填 Base URL"
        return "❌ Base URL 指向的是公网服务，必须填 API Key（本地/局域网地址才允许留空）"
    if mode == "anthropic":
        if not (config.anthropic_base_url or "").strip():
            return "❌ 还没填 Base URL（cliproxy 反代就填它的地址，如 http://192.168.1.10:8317）"
        if not (config.anthropic_model or "").strip():
            return "❌ 还没填模型名（点「列出可用模型」可以拉一份列表）"
        return "❌ Base URL 指向的是公网服务，必须填 API Key（局域网反代才允许留空）"
    if mode == "ollama":
        return "❌ 还没填 Ollama 地址（容器里访问宿主机填 http://host.docker.internal:11434）"
    if mode == "gemini":
        return "❌ Gemini 需要 API Key 与模型名（点「列出可用模型」可以拉一份列表）"
    return "❌ 配置不完整"


def build_llm(config: AppConfig) -> BaseLLM:
    cls = PROVIDERS.get(config.llm_mode)
    if cls is None:
        raise LLMError(f"未知的 LLM 通道：{config.llm_mode}")
    return cls(config)


async def test_connection(config: AppConfig) -> tuple[bool, str, str]:
    """返回 (是否成功, 说明, 模型名)。不抛异常，供 WebUI 直接展示。"""
    if not is_configured(config):
        return (config.llm_mode == "off"), describe_missing(config), ""

    llm = build_llm(config)
    probe = [
        {"role": "system", "content": "你是测试助手，只输出 JSON。"},
        {"role": "user", "content": '请只返回这个 JSON：{"ok": true, "msg": "连接正常"}'},
    ]
    try:
        result = await llm.chat(probe, json_mode=True)
    except LLMError as exc:
        return False, f"❌ {exc}", ""
    except Exception as exc:  # pragma: no cover - 兜底
        return False, f"❌ 未预期错误：{exc}", ""
    finally:
        await llm.aclose()

    preview = (result.text or "").strip().replace("\n", " ")[:120]
    if not preview:
        return False, "❌ 接口返回空内容", result.model
    label = PROVIDER_LABELS.get(result.provider, result.provider)
    return True, f"✅ {label} 连接成功（{result.elapsed_ms} ms）· 返回：{preview}", result.model


async def list_models(config: AppConfig) -> tuple[bool, str, list[str]]:
    """拉取当前通道的可用模型列表，返回 (是否成功, 说明, 模型名列表)。

    这对手填模型名很痛苦的反代/网关特别有用 —— 不用去翻文档猜别名。
    """
    if config.llm_mode == "off":
        return False, "当前是「仅本地菜谱库」模式，没有模型列表", []

    llm = build_llm(config)
    try:
        models = await llm.list_models()
    except LLMError as exc:
        return False, f"❌ {exc}", []
    except Exception as exc:  # pragma: no cover - 兜底
        return False, f"❌ 获取模型列表失败：{exc}", []
    finally:
        await llm.aclose()

    if not models:
        return False, "对方没有返回模型列表（不是所有反代都实现 /models），手动填模型名即可", []
    return True, f"✅ 拿到 {len(models)} 个模型", models
