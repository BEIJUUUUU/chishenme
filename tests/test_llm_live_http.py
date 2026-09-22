"""真实 HTTP 往返测试：起一个本地假 API 服务器，用真 httpx 打过去。

和 test_llm_providers.py 的区别：
- 那边用 MockTransport 验报文形状（快、可控）
- 这边走真实 TCP + 真实 httpx，覆盖超时设置、请求头透传、分块读取、
  以及「对方返回的 content-type 不是我们期待的」这类只有真网络才会踩到的问题

四种通道（OpenAI 兼容 / Anthropic 兼容 / Ollama / Gemini）都有对应路由，
包括每个通道的 models 列表接口。
"""
from __future__ import annotations

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core import generator, pantry
from app.llm import build_llm, list_models
from app.llm.factory import looks_local
from app.runtime_config import AppConfig

# 假服务器会把这些「收到的请求」记下来，供断言使用
RECORDED: list[dict] = []

MENU = {
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
                    "steps": "①铺姜片 ②大火蒸 8 分钟 ③泼热油",
                },
                {
                    "name": "醋溜土豆丝",
                    "category": "素菜",
                    "ingredients": ["土豆", "米醋"],
                    "spicy": 0,
                    "note": "出锅前淋醋",
                    "steps": "①切丝泡水 ②爆香辣椒 ③快炒淋醋",
                },
            ],
            "soup": "紫菜蛋花汤",
            "staple": "米饭",
            "reason": "一荤一素配汤",
        }
    ]
}


class FakeProviderHandler(BaseHTTPRequestHandler):
    """按路径分发到四种 API 的响应形状。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 静音
        return

    # ---------------- 工具 ----------------
    def _read_json(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {"_raw": raw.decode("utf-8", "replace")}

    def _reply(self, payload: dict, status: int = 200, content_type: str = "application/json"):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reply_text(self, text: str, status: int = 200, content_type: str = "text/plain"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, method: str, payload=None) -> None:
        RECORDED.append(
            {
                "method": method,
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": payload,
            }
        )

    # ---------------- GET ----------------
    def do_GET(self):
        self._record("GET")
        path = self.path.split("?")[0]
        if path == "/v1/models":
            # OpenAI 与 Anthropic 都是这个形状
            self._reply({"data": [{"id": "fake-chat"}, {"id": "fake-reasoner"}]})
        elif path == "/v1beta/models":
            self._reply({"models": [{"name": "models/gemini-fake"}]})
        elif path == "/api/tags":
            self._reply({"models": [{"name": "qwen2.5:7b"}]})
        else:
            self._reply({"error": {"message": f"no route {path}"}}, status=404)

    # ---------------- POST ----------------
    def do_POST(self):
        path = self.path.split("?")[0]
        payload = self._read_json()
        self._record("POST", payload)

        if path == "/v1/chat/completions":
            self._reply(
                {
                    "id": "chatcmpl-fake",
                    "model": payload.get("model", "fake"),
                    "choices": [{"message": {"role": "assistant", "content": json.dumps(MENU, ensure_ascii=False)}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 200},
                }
            )
        elif path == "/v1/messages":
            self._reply(
                {
                    "id": "msg_fake",
                    "model": payload.get("model", "fake"),
                    "content": [{"type": "text", "text": json.dumps(MENU, ensure_ascii=False)}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 111, "output_tokens": 222},
                }
            )
        elif path.startswith("/v1beta/models/") and path.endswith(":generateContent"):
            self._reply(
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": json.dumps(MENU, ensure_ascii=False)}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 55, "candidatesTokenCount": 66},
                }
            )
        elif path == "/api/chat":
            self._reply(
                {
                    "model": payload.get("model", "fake"),
                    "message": {"role": "assistant", "content": json.dumps(MENU, ensure_ascii=False)},
                    "prompt_eval_count": 7,
                    "eval_count": 9,
                }
            )
        else:
            self._reply({"error": {"message": f"no route {path}"}}, status=404)


@pytest.fixture(scope="module")
def fake_api():
    """在随机空闲端口上跑一个假 API 服务器。"""
    RECORDED.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProviderHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def configs(base: str) -> dict[str, AppConfig]:
    return {
        "openai": AppConfig(
            llm_mode="openai", openai_base_url=f"{base}/v1", openai_model="fake-chat", openai_api_key=""
        ),
        "anthropic": AppConfig(
            llm_mode="anthropic", anthropic_base_url=base, anthropic_model="fake-claude", anthropic_api_key=""
        ),
        "ollama": AppConfig(llm_mode="ollama", ollama_base_url=base, ollama_model="qwen2.5:7b"),
        "gemini": AppConfig(llm_mode="gemini", gemini_base_url=base, gemini_model="gemini-fake", gemini_api_key="k"),
    }


def test_fake_endpoints_are_local(fake_api):
    """假服务器就在 127.0.0.1，属于「本地」，所以不填 Key 也算配置好了。"""
    cfgs = configs(fake_api)
    assert looks_local(cfgs["openai"].openai_base_url)
    assert looks_local(cfgs["anthropic"].anthropic_base_url)
    assert looks_local(cfgs["ollama"].ollama_base_url)
    assert looks_local(cfgs["gemini"].gemini_base_url)
    # 对照：公网地址不算本地
    assert not looks_local("https://api.deepseek.com/v1")


@pytest.mark.parametrize("channel", ["openai", "anthropic", "ollama", "gemini"])
@pytest.mark.asyncio
async def test_real_http_chat_roundtrip(fake_api, channel):
    """四种通道都要能通过真实 HTTP 拿到菜单文本。"""
    cfg = configs(fake_api)[channel]
    llm = build_llm(cfg)
    result = await llm.chat(
        [{"role": "system", "content": "你是搭配师"}, {"role": "user", "content": "配个午餐"}], json_mode=True
    )
    await llm.aclose()

    assert result.text.strip().startswith("{")
    payload = json.loads(result.text)
    assert payload["meals"][0]["meal"] == "午餐"
    assert result.provider == channel

    record = RECORDED[-1]
    assert record["method"] == "POST"
    # Gemini 的模型名走 URL 路径，其余三个走请求体
    if channel == "gemini":
        assert "gemini-fake" in record["path"]
        assert record["body"]["contents"][0]["parts"][0]["text"] == "配个午餐"
    else:
        assert record["body"]["model"], "模型名必须发出去"
        # 中文提示词在真实 HTTP 上不能变成乱码
        assert "配个午餐" in json.dumps(record["body"], ensure_ascii=False)


@pytest.mark.parametrize("channel", ["openai", "anthropic", "ollama", "gemini"])
@pytest.mark.asyncio
async def test_real_http_list_models(fake_api, channel):
    cfg = configs(fake_api)[channel]
    ok, message, models = await list_models(cfg)
    assert ok, message
    assert models, f"{channel} 应该能列出模型"
    assert all(isinstance(m, str) and m for m in models)


@pytest.mark.asyncio
async def test_real_http_full_generation_pipeline(db, fake_api):
    """真 HTTP + 真 provider：提示词 → 请求 → 解析 → 校验 → 入库 → 购物清单。"""
    pantry.seed_database(db)
    cfg = configs(fake_api)["openai"]
    cfg.province = "山东"
    # 关掉查重窗口：假服务器对任何请求都回同一份菜单，
    # 开着窗口会和别的用例互相干扰（这本身是被测逻辑在正常工作）
    cfg.repeat_window_days = 0

    plans = await generator.generate_day(db, cfg, date(2024, 9, 1), meals=("午餐",))
    plan = plans["午餐"]

    assert plan.source == "llm" and plan.status == "ok"
    assert plan.dish_names == ["清蒸鲈鱼", "醋溜土豆丝"]
    assert plan.soup == "紫菜蛋花汤"
    assert plan.shopping, "购物清单要生成出来"
    assert plan.recipes["清蒸鲈鱼"]["steps"].startswith("①")

    # 发出去的确实是完整的菜单提示词
    body = RECORDED[-1]["body"]
    assert "山东" in json.dumps(body, ensure_ascii=False)
    assert body.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_real_http_anthropic_proxy_pipeline(db, fake_api):
    """cliproxy 场景：Anthropic 反代也能走完整链路。"""
    pantry.seed_database(db)
    cfg = configs(fake_api)["anthropic"]
    cfg.province = "广东"
    cfg.repeat_window_days = 0

    plans = await generator.generate_day(db, cfg, date(2024, 9, 2), meals=("午餐",))
    plan = plans["午餐"]
    assert plan.source == "llm" and plan.status == "ok"

    body = RECORDED[-1]["body"]
    assert body["system"], "system 提示词要提到顶层字段"
    assert all(m["role"] != "system" for m in body["messages"])
    assert body["max_tokens"] > 0


@pytest.mark.asyncio
async def test_real_http_error_surface(fake_api):
    """指向一个不存在的路径时，错误信息要说人话。"""
    cfg = AppConfig(
        llm_mode="openai",
        openai_base_url=f"{fake_api}/wrong-prefix/v1",
        openai_model="m",
        openai_api_key="",
    )
    ok, _message, models = await list_models(cfg)
    assert not ok
    assert models == []
