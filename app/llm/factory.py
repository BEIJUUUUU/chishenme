"""通道工厂与连通性自检。"""
from __future__ import annotations

from ..runtime_config import AppConfig
from .base import BaseLLM, LLMError
from .ollama_provider import OllamaLLM
from .openai_compat import OpenAICompatLLM

PROVIDERS: dict[str, type[BaseLLM]] = {
    "openai": OpenAICompatLLM,
    "ollama": OllamaLLM,
}

PROVIDER_LABELS = {
    "off": "仅本地菜谱库",
    "openai": "OpenAI 兼容 API",
    "ollama": "本地 Ollama",
}


def is_configured(config: AppConfig) -> bool:
    """是否真的能调到大模型。

    这是「零配置可用」的关键：没配置就走本地菜谱库，不再白等重试、不再刷错误日志。
    """
    mode = config.llm_mode
    if mode == "off":
        return False
    if mode == "openai":
        return bool((config.openai_api_key or "").strip() and (config.openai_base_url or "").strip())
    if mode == "ollama":
        return bool((config.ollama_base_url or "").strip())
    return False


def build_llm(config: AppConfig) -> BaseLLM:
    cls = PROVIDERS.get(config.llm_mode)
    if cls is None:
        raise LLMError(f"未知的 LLM 通道：{config.llm_mode}")
    return cls(config)


async def test_connection(config: AppConfig) -> tuple[bool, str, str]:
    """返回 (是否成功, 说明, 模型名)。不抛异常，供 WebUI 直接展示。"""
    if not is_configured(config):
        if config.llm_mode == "off":
            return (
                True,
                (
                    "当前是「仅本地菜谱库」模式：不调用大模型，用内置家常菜按时令与忌口搭配，完全离线可用。"
                    "想让 AI 自由配菜，把通道切成 OpenAI 兼容 API 或本地 Ollama 即可。"
                ),
                "",
            )
        if config.llm_mode == "openai":
            return False, "❌ 还没填 API Key（或 Base URL 为空）", ""
        return False, "❌ 还没填 Ollama 地址", ""

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
    return True, f"✅ 连接成功（{result.elapsed_ms} ms）· 返回：{preview}", result.model
