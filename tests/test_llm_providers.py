"""LLM 通道测试：用 httpx MockTransport 拦住真实网络请求。

这里测的是「发给对方的报文长什么样」和「对方各种奇怪返回怎么解析」——
cliproxy、one-api 这类反代最容易在这两处翻车，所以不能只测 happy path。
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.core import generator, pantry
from app.llm import LLMError, build_llm, is_configured, list_models, parse_extra_headers
from app.llm import test_connection as llm_test_connection
from app.llm.anthropic_compat import parse_sse_text
from app.llm.factory import looks_local
from app.runtime_config import AppConfig


# ---------------------------------------------------------------------------
# 测试用的 HTTP 替身
# ---------------------------------------------------------------------------
@pytest.fixture()
def http(monkeypatch):
    """把 httpx.AsyncClient 换成带 MockTransport 的版本，并记录所有出站请求。"""
    real_client = httpx.AsyncClient  # 先抓住真身，否则下面会递归调用自己
    state = SimpleNamespace(requests=[], handler=None, responses=[])

    def fake_client(**kwargs):
        kwargs.pop("transport", None)

        def handler(request: httpx.Request) -> httpx.Response:
            state.requests.append(request)
            if callable(state.handler):
                return state.handler(request)
            if state.responses:
                return state.responses.pop(0)
            return httpx.Response(500, json={"error": "测试没有安排响应"})

        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    return state


def openai_body(content: str = '{"ok": true}', model: str = "test-model") -> dict:
    return {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }


def anthropic_body(text: str = '{"ok": true}', model: str = "claude-test") -> dict:
    return {
        "id": "msg_test",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 33, "output_tokens": 44},
    }


def gemini_body(text: str = '{"ok": true}') -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 55, "candidatesTokenCount": 66},
    }


# ---------------------------------------------------------------------------
# 地址判定：本地/局域网不需要 Key
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://127.0.0.1:1234/v1", True),
        ("http://localhost:8080/v1", True),
        ("http://host.docker.internal:11434", True),
        ("http://192.168.1.10:8317", True),
        ("http://10.0.0.5:8000/v1", True),
        ("http://172.16.5.5:8000/v1", True),
        ("https://api.deepseek.com/v1", False),
        ("https://api.anthropic.com", False),
        ("https://some-proxy.example.com/v1", False),
    ],
)
def test_looks_local(url, expected):
    assert looks_local(url) is expected


def test_is_configured_matrix():
    # 本地 OpenAI 兼容服务：不填 Key 也算配好（LM Studio / llama.cpp 就是这样）
    assert is_configured(AppConfig(llm_mode="openai", openai_base_url="http://127.0.0.1:1234/v1"))
    # 公网服务必须有 Key，否则只会收获一串 401
    assert not is_configured(AppConfig(llm_mode="openai", openai_base_url="https://api.deepseek.com/v1"))
    assert is_configured(
        AppConfig(
            llm_mode="openai",
            openai_base_url="https://api.deepseek.com/v1",
            openai_api_key="sk-x",
        )
    )
    # cliproxy 这类局域网反代：地址 + 模型名即可
    assert is_configured(
        AppConfig(llm_mode="anthropic", anthropic_base_url="http://192.168.1.10:8317", anthropic_model="claude-x")
    )
    # 缺模型名不行 —— 反代不会替你猜
    assert not is_configured(AppConfig(llm_mode="anthropic", anthropic_base_url="http://192.168.1.10:8317"))
    # Gemini 必须要 Key + 模型名
    assert not is_configured(AppConfig(llm_mode="gemini", gemini_api_key="k"))
    assert is_configured(AppConfig(llm_mode="gemini", gemini_api_key="k", gemini_model="gemini-2.5-flash"))
    # off / ollama
    assert not is_configured(AppConfig(llm_mode="off"))
    assert is_configured(AppConfig(llm_mode="ollama", ollama_base_url="http://127.0.0.1:11434"))


def test_parse_extra_headers():
    raw = "X-Api-Key: abc\n# 注释行\n\n  X-Token :t2  \n没有冒号的行\n: 空key"
    assert parse_extra_headers(raw) == {"X-Api-Key": "abc", "X-Token": "t2"}
    assert parse_extra_headers("") == {}


# ---------------------------------------------------------------------------
# OpenAI 兼容
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_openai_request_shape(http):
    http.responses = [httpx.Response(200, json=openai_body())]
    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url="https://api.deepseek.com/v1",
        openai_api_key="sk-test",
        openai_model="deepseek-chat",
        llm_temperature=0.5,
    )
    result = await build_llm(cfg).chat(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}], json_mode=True
    )

    req = http.requests[0]
    assert str(req.url) == "https://api.deepseek.com/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer sk-test"
    payload = json.loads(req.content)
    assert payload["model"] == "deepseek-chat"
    assert payload["temperature"] == 0.5
    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    # OpenAI 兼容通道刻意不发送 max_tokens：部分服务（如 o1 系）会因此报错
    assert "max_tokens" not in payload

    assert result.text == '{"ok": true}'
    assert result.prompt_tokens == 11 and result.completion_tokens == 22
    assert result.model == "test-model"


@pytest.mark.asyncio
async def test_openai_local_service_has_no_auth_header(http):
    http.responses = [httpx.Response(200, json=openai_body())]
    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url="http://127.0.0.1:1234/v1",
        openai_api_key="",
        openai_model="local-model",
    )
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert "authorization" not in http.requests[0].headers


@pytest.mark.asyncio
async def test_openai_full_url_and_suffix_handling(http):
    """用户可能把完整 endpoint 直接粘进 Base URL，不能拼出 /chat/completions/chat/completions。"""
    http.responses = [httpx.Response(200, json=openai_body())]
    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url="https://api.example.com/v1/chat/completions",
        openai_api_key="k",
        openai_model="m",
    )
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert str(http.requests[0].url) == "https://api.example.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_openai_extra_headers_are_sent(http):
    http.responses = [httpx.Response(200, json=openai_body())]
    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url="https://proxy.example.com/v1",
        openai_api_key="k",
        openai_model="m",
        llm_extra_headers="X-Api-Key: custom\nX-Token: t2",
    )
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    req = http.requests[0]
    assert req.headers["x-api-key"] == "custom"
    assert req.headers["x-token"] == "t2"


@pytest.mark.asyncio
async def test_openai_json_mode_can_be_disabled(http):
    http.responses = [httpx.Response(200, json=openai_body())]
    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url="http://127.0.0.1:1234/v1",
        openai_model="m",
        llm_json_mode=False,
    )
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert "response_format" not in json.loads(http.requests[0].content)


@pytest.mark.asyncio
async def test_openai_error_mapping(http):
    http.responses = [httpx.Response(401, text="bad key")]
    cfg = AppConfig(
        llm_mode="openai", openai_base_url="https://x.example.com/v1", openai_api_key="k", openai_model="m"
    )
    with pytest.raises(LLMError) as exc:
        await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert "鉴权失败" in str(exc.value)

    http.responses = [httpx.Response(200, json={"error": {"message": "模型不存在"}})]
    with pytest.raises(LLMError) as exc:
        await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert "模型不存在" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_list_models(http):
    http.responses = [
        httpx.Response(200, json={"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]})
    ]
    cfg = AppConfig(
        llm_mode="openai", openai_base_url="https://x.example.com/v1", openai_api_key="k", openai_model="m"
    )
    models = await build_llm(cfg).list_models()
    assert models == ["a-model", "b-model"]
    assert str(http.requests[0].url) == "https://x.example.com/v1/models"


# ---------------------------------------------------------------------------
# Anthropic 兼容（cliproxy 反代走这条）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_anthropic_request_shape_for_cliproxy(http):
    http.responses = [httpx.Response(200, json=anthropic_body())]
    cfg = AppConfig(
        llm_mode="anthropic",
        anthropic_base_url="http://192.168.1.10:8317",
        anthropic_api_key="",  # 反代通常不校验
        anthropic_model="claude-sonnet-4-5",
    )
    llm = build_llm(cfg)
    result = await llm.chat(
        [{"role": "system", "content": "你是搭配师"}, {"role": "user", "content": "配个菜"}], json_mode=True
    )

    req = http.requests[0]
    assert str(req.url) == "http://192.168.1.10:8317/v1/messages"
    assert req.headers["anthropic-version"] == "2023-06-01"
    assert "x-api-key" not in req.headers  # 没填 Key 就不发这个头

    payload = json.loads(req.content)
    assert payload["model"] == "claude-sonnet-4-5"
    assert payload["max_tokens"] == cfg.llm_max_tokens  # Messages API 必须显式给
    assert payload["system"] == "你是搭配师"  # system 提到顶层
    assert payload["stream"] is False
    # messages 里不能有 system 角色
    assert [m["role"] for m in payload["messages"]] == ["user"]
    assert "response_format" not in payload  # Messages API 没有这个参数

    assert result.text == '{"ok": true}'
    assert result.prompt_tokens == 33 and result.completion_tokens == 44
    assert result.provider == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_official_url_and_key_header(http):
    http.responses = [httpx.Response(200, json=anthropic_body())]
    cfg = AppConfig(
        llm_mode="anthropic",
        anthropic_base_url="https://api.anthropic.com",
        anthropic_api_key="sk-ant-xxx",
        anthropic_model="claude-sonnet-4-5",
    )
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    req = http.requests[0]
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "sk-ant-xxx"


@pytest.mark.asyncio
async def test_anthropic_accepts_v1_base_and_full_endpoint(http):
    cfg = AppConfig(
        llm_mode="anthropic", anthropic_base_url="http://10.0.0.9:8082/v1", anthropic_model="m"
    )
    http.responses = [httpx.Response(200, json=anthropic_body())]
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert str(http.requests[0].url) == "http://10.0.0.9:8082/v1/messages"

    cfg2 = AppConfig(
        llm_mode="anthropic", anthropic_base_url="http://10.0.0.9:8082/v1/messages", anthropic_model="m"
    )
    http.responses = [httpx.Response(200, json=anthropic_body())]
    await build_llm(cfg2).chat([{"role": "user", "content": "hi"}])
    assert str(http.requests[1].url) == "http://10.0.0.9:8082/v1/messages"


@pytest.mark.asyncio
async def test_anthropic_parses_sse_when_proxy_ignores_stream_false(http):
    """有些反代无视 stream=false 直接吐 SSE，不能因此判定失败。"""
    sse = "\n".join(
        [
            "event: message_start",
            'data: {"type":"message_start","message":{"id":"msg_1"}}',
            "",
            "event: content_block_delta",
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"{\\"meals\\":"}}',
            "",
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"[]}"}}',
            "",
            "data: [DONE]",
        ]
    )
    http.responses = [httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})]
    cfg = AppConfig(
        llm_mode="anthropic", anthropic_base_url="http://192.168.1.10:8317", anthropic_model="m"
    )
    result = await build_llm(cfg).chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert result.text == '{"meals":[]}'
    assert json.loads(result.text) == {"meals": []}


def test_parse_sse_text_handles_noise():
    assert parse_sse_text("") == ""
    assert parse_sse_text("data: 不是JSON\n\n") == ""
    assert parse_sse_text('data: {"delta":{"text":"a"}}\ndata: [DONE]') == "a"
    # 整块返回（content_block）也要能取到
    assert parse_sse_text('data: {"content_block":{"text":"整块"}}') == "整块"


@pytest.mark.asyncio
async def test_anthropic_error_and_model_list(http):
    http.responses = [httpx.Response(400, json={"type": "error", "error": {"message": "bad model"}})]
    cfg = AppConfig(
        llm_mode="anthropic", anthropic_base_url="http://127.0.0.1:8317", anthropic_model="bad"
    )
    with pytest.raises(LLMError):
        await build_llm(cfg).chat([{"role": "user", "content": "hi"}])

    http.responses = [httpx.Response(200, json={"data": [{"id": "claude-b"}, {"id": "claude-a"}]})]
    assert await build_llm(cfg).list_models() == ["claude-a", "claude-b"]
    assert str(http.requests[1].url) == "http://127.0.0.1:8317/v1/models"


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ollama_request_shape_and_parse(http):
    http.responses = [
        httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "prompt_eval_count": 7,
                "eval_count": 9,
            },
        )
    ]
    cfg = AppConfig(llm_mode="ollama", ollama_base_url="http://host.docker.internal:11434", ollama_model="qwen2.5:7b")
    result = await build_llm(cfg).chat([{"role": "user", "content": "hi"}], json_mode=True)
    req = http.requests[0]
    assert str(req.url) == "http://host.docker.internal:11434/api/chat"
    payload = json.loads(req.content)
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == cfg.llm_temperature
    assert result.text == '{"ok": true}'
    assert result.prompt_tokens == 7 and result.completion_tokens == 9


@pytest.mark.asyncio
async def test_ollama_missing_model_message(http):
    http.responses = [httpx.Response(404, text="model not found")]
    cfg = AppConfig(llm_mode="ollama", ollama_base_url="http://127.0.0.1:11434", ollama_model="nope")
    with pytest.raises(LLMError) as exc:
        await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert "ollama pull nope" in str(exc.value)


@pytest.mark.asyncio
async def test_ollama_list_models(http):
    http.responses = [httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:8b"}]})]
    cfg = AppConfig(llm_mode="ollama", ollama_base_url="http://127.0.0.1:11434", ollama_model="x")
    assert await build_llm(cfg).list_models() == ["qwen2.5:7b", "llama3:8b"]


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_request_shape_and_parse(http):
    http.responses = [httpx.Response(200, json=gemini_body())]
    cfg = AppConfig(
        llm_mode="gemini",
        gemini_base_url="https://generativelanguage.googleapis.com",
        gemini_api_key="g-key",
        gemini_model="gemini-2.5-flash",
    )
    llm = build_llm(cfg)
    result = await llm.chat(
        [{"role": "system", "content": "你是搭配师"}, {"role": "user", "content": "配个菜"}], json_mode=True
    )

    req = http.requests[0]
    assert str(req.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert req.headers["x-goog-api-key"] == "g-key"
    payload = json.loads(req.content)
    assert payload["systemInstruction"]["parts"][0]["text"] == "你是搭配师"
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["maxOutputTokens"] == cfg.llm_max_tokens
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "配个菜"}]}]

    assert result.text == '{"ok": true}'
    assert result.prompt_tokens == 55 and result.completion_tokens == 66


@pytest.mark.asyncio
async def test_gemini_custom_base_and_missing_model(http):
    http.responses = [httpx.Response(200, json=gemini_body())]
    cfg = AppConfig(
        llm_mode="gemini", gemini_base_url="http://192.168.1.20:8000", gemini_api_key="k", gemini_model="m"
    )
    await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert str(http.requests[0].url) == "http://192.168.1.20:8000/v1beta/models/m:generateContent"

    with pytest.raises(LLMError) as exc:
        await build_llm(AppConfig(llm_mode="gemini", gemini_api_key="k", gemini_model="")).chat(
            [{"role": "user", "content": "hi"}]
        )
    assert "模型名" in str(exc.value)


@pytest.mark.asyncio
async def test_gemini_blocked_and_list_models(http):
    http.responses = [
        httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []})
    ]
    cfg = AppConfig(llm_mode="gemini", gemini_api_key="k", gemini_model="m")
    with pytest.raises(LLMError) as exc:
        await build_llm(cfg).chat([{"role": "user", "content": "hi"}])
    assert "安全策略" in str(exc.value)

    http.responses = [httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-flash"}]})]
    assert await build_llm(cfg).list_models() == ["gemini-2.5-flash"]


# ---------------------------------------------------------------------------
# 工厂级：连通性自检与模型列表
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_test_connection_success_and_failure(http):
    http.responses = [httpx.Response(200, json=openai_body('{"ok": true, "msg": "连接正常"}'))]
    cfg = AppConfig(
        llm_mode="openai", openai_base_url="http://127.0.0.1:1234/v1", openai_model="local"
    )
    ok, message, model = await llm_test_connection(cfg)
    assert ok and "连接成功" in message and model == "test-model"

    http.responses = [httpx.Response(500, text="boom")]
    ok, message, _ = await llm_test_connection(cfg)
    assert not ok and message.startswith("❌")


@pytest.mark.asyncio
async def test_test_connection_explains_missing_config():
    ok, message, _ = await llm_test_connection(AppConfig(llm_mode="off"))
    assert ok and "仅本地菜谱库" in message

    ok, message, _ = await llm_test_connection(
        AppConfig(llm_mode="anthropic", anthropic_base_url="http://192.168.1.9:8317")
    )
    assert not ok and "模型名" in message

    ok, message, _ = await llm_test_connection(
        AppConfig(llm_mode="openai", openai_base_url="https://api.deepseek.com/v1")
    )
    assert not ok and "API Key" in message


@pytest.mark.asyncio
async def test_list_models_wrapper(http):
    ok, message, models = await list_models(AppConfig(llm_mode="off"))
    assert not ok and models == [] and "仅本地菜谱库" in message

    http.responses = [httpx.Response(200, json={"data": [{"id": "m1"}]})]
    ok, message, models = await list_models(
        AppConfig(llm_mode="openai", openai_base_url="https://x.example.com/v1", openai_api_key="k", openai_model="m")
    )
    assert ok and models == ["m1"] and "1 个模型" in message

    # 反代没实现 /models 时要给出可操作的提示，而不是干巴巴地失败
    http.responses = [httpx.Response(404, text="not found")]
    ok, message, models = await list_models(
        AppConfig(
            llm_mode="anthropic",
            anthropic_base_url="http://192.168.1.9:8317",
            anthropic_model="m",
        )
    )
    assert not ok and "手动填模型名" in message


# ---------------------------------------------------------------------------
# 端到端：真的用 provider + 假 HTTP 走完整生成链路
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_day_through_openai_provider(db, http):
    """真实 provider + 假网络：提示词 → HTTP → 解析 → 校验 → 入库 全链路。"""
    pantry.seed_database(db)
    menu = {
        "meals": [
            {
                "meal": "午餐",
                "dishes": [
                    {
                        "name": "清蒸鲈鱼",
                        "category": "荤菜",
                        "ingredients": ["鲈鱼", "姜"],
                        "spicy": 0,
                        "note": "水开蒸 8 分钟",
                        "steps": "①铺姜片 ②大火蒸 8 分钟 ③泼热油淋豉油",
                    },
                    {
                        "name": "清炒西兰花",
                        "category": "素菜",
                        "ingredients": ["西兰花", "蒜"],
                        "spicy": 0,
                        "note": "焯水后再炒",
                        "steps": "①掰小朵焯 1 分钟 ②蒜末爆香 ③快炒加盐",
                    },
                ],
                "soup": "紫菜蛋花汤",
                "staple": "米饭",
                "reason": "清淡好消化",
            }
        ]
    }
    http.responses = [httpx.Response(200, json=openai_body(json.dumps(menu, ensure_ascii=False)))]

    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url="http://127.0.0.1:1234/v1",
        openai_model="local-model",
        province="山东",
    )
    plans = await generator.generate_day(db, cfg, date(2024, 8, 1), meals=("午餐",))

    plan = plans["午餐"]
    assert plan.source == "llm" and plan.status == "ok"
    assert plan.dish_names == ["清蒸鲈鱼", "清炒西兰花"]
    assert plan.recipes["清蒸鲈鱼"]["steps"].startswith("①")
    # 提示词确实发给了对方，并且要求了 JSON
    payload = json.loads(http.requests[0].content)
    assert payload["response_format"] == {"type": "json_object"}
    assert "JSON" in payload["messages"][1]["content"]


@pytest.mark.asyncio
async def test_generate_day_through_cliproxy_style_anthropic(db, http):
    """同一条链路换 Anthropic 反代：验证 cliproxy 场景也能端到端跑通。"""
    pantry.seed_database(db)
    menu = {
        "meals": [
            {
                "meal": "晚餐",
                "dishes": [
                    {
                        "name": "西红柿炒鸡蛋",
                        "category": "素菜",
                        "ingredients": ["西红柿", "鸡蛋"],
                        "spicy": 0,
                        "note": "蛋先炒熟盛出",
                        "steps": "①蛋炒熟盛出 ②番茄炒出汁 ③回锅翻匀",
                    },
                    {
                        "name": "红烧肉",
                        "category": "荤菜",
                        "ingredients": ["五花肉", "冰糖"],
                        "spicy": 0,
                        "note": "小火炖 40 分钟",
                        "steps": "①焯水 ②炒糖色 ③炖 40 分钟收汁",
                    },
                ],
                "soup": "冬瓜排骨汤",
                "staple": "米饭",
                "reason": "一荤一素",
            }
        ]
    }
    http.responses = [httpx.Response(200, json=anthropic_body(json.dumps(menu, ensure_ascii=False)))]

    cfg = AppConfig(
        llm_mode="anthropic",
        anthropic_base_url="http://192.168.1.10:8317",
        anthropic_model="claude-sonnet-4-5",
    )
    plans = await generator.generate_day(db, cfg, date(2024, 8, 2), meals=("晚餐",))

    plan = plans["晚餐"]
    assert plan.source == "llm" and plan.status == "ok"
    assert "红烧肉" in plan.dish_names
    assert plan.soup == "冬瓜排骨汤"
    payload = json.loads(http.requests[0].content)
    assert payload["system"]
    assert all(m["role"] != "system" for m in payload["messages"])
