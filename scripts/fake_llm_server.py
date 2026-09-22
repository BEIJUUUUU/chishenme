#!/usr/bin/env python
"""本地假模型服务器：模拟 OpenAI / Anthropic / Ollama / Gemini 四种接口。

    python scripts/fake_llm_server.py --port 877

用途：
1. **不花一分钱验证配置链路** —— 在「设置 → LLM 模型」里把地址指向本脚本，
   点「测试连接」和「列出可用模型」，再生成菜单，整条链路就跑通了。
2. 开发时不想每次调用真模型，用它顶着。
3. 排查「到底是我的配置错了，还是对面的模型不行」。

它从仓库自带的菜谱库随机拼菜单，所以每次请求返回的菜不一样，
能顺便验证「防重复」逻辑是不是在工作。

支持的路由：
    POST /v1/chat/completions                      OpenAI 兼容
    GET  /v1/models                                模型列表
    POST /v1/messages                              Anthropic 兼容
    POST /api/chat                                 Ollama
    GET  /api/tags                                 Ollama 模型列表
    POST /v1beta/models/{model}:generateContent    Gemini
    GET  /v1beta/models                            Gemini 模型列表
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.pantry import MEAT, SOUP, VEG, load_seed_dishes_with_howto

DISHES = load_seed_dishes_with_howto()


def parse_constraints(text: str) -> dict:
    """从提示词里把「餐次 / 菜数 / 辣度上限 / 忌口食材」读出来。

    这样假模型也会守规矩：不然随机挑到重辣菜、或者菜数不对，
    会被本项目的校验闸门拦下，用户会误以为是自己配置错了。
    """
    spicy = 3
    match = re.search(r"辣度上限[:：]\s*(\d)", text)
    if match:
        spicy = int(match.group(1))

    avoid: list[str] = []
    match = re.search(r"忌口食材[^:：]*[:：]\s*(.+)", text)
    if match:
        avoid = [part.strip() for part in re.split(r"[、,，]", match.group(1)) if part.strip()]

    meal, count = "午餐", 4
    match = re.search(r"(午餐|晚餐)[:：]\s*(\d+)\s*道菜", text)
    if match:
        meal, count = match.group(1), int(match.group(2))

    return {"meal": meal, "count": max(1, min(8, count)), "spicy": spicy, "avoid": avoid}


def build_menu(meal: str = "午餐", count: int = 4, spicy_limit: int = 3, avoid: list[str] | None = None) -> dict:
    """从自带菜谱库随机拼一桌，带上真实的做法，并遵守传入的约束。"""
    avoid = avoid or []

    def usable(dish: dict) -> bool:
        if int(dish.get("spicy", 0)) > spicy_limit:
            return False
        text = dish["name"] + "".join(dish.get("ingredients", []))
        return not any(token and token in text for token in avoid)

    def pick(category: str, wanted: int, exclude: set[str]) -> list[dict]:
        if wanted <= 0:
            return []
        pool = [d for d in DISHES if d["category"] == category and d["name"] not in exclude and usable(d)]
        if not pool:  # 约束太严时放宽，保证假模型总能给出东西
            pool = [d for d in DISHES if d["category"] == category and d["name"] not in exclude]
        random.shuffle(pool)
        chosen = pool[:wanted]
        exclude.update(d["name"] for d in chosen)
        return chosen

    # 荤素大致五五开，至少各一道
    n_meat = max(1, round(count * 0.5)) if count >= 2 else 1
    n_veg = max(1, count - n_meat) if count >= 2 else 0

    used: set[str] = set()
    dishes = []
    for dish in pick(MEAT, n_meat, used) + pick(VEG, n_veg, used):
        dishes.append(
            {
                "name": dish["name"],
                "category": dish["category"],
                "ingredients": dish["ingredients"],
                "spicy": dish.get("spicy", 0),
                "note": dish.get("howto", ""),
                "steps": dish.get("steps", ""),
            }
        )
    soups = pick(SOUP, 1, used)
    return {
        "meals": [
            {
                "meal": meal,
                "dishes": dishes,
                "soup": soups[0]["name"] if soups else "",
                "staple": random.choice(["米饭", "馒头", "面条"]),
                "reason": "本地假模型随机搭配，用于验证链路。",
            }
        ]
    }


def extract_prompt(payload: dict) -> str:
    """把四种 API 形状里的提示词文本拼出来，供约束解析使用。"""
    parts: list[str] = []

    def feed(value) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                feed(item)
        elif isinstance(value, dict):
            if "text" in value:
                feed(value["text"])
            if "parts" in value:
                feed(value["parts"])
            if "content" in value:
                feed(value["content"])

    feed(payload.get("system"))
    feed(payload.get("systemInstruction"))
    feed(payload.get("messages"))
    feed(payload.get("contents"))
    return "\n".join(parts)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write(f"  · {self.command} {self.path}\n")

    # ---------------- 工具 ----------------
    def _body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {}

    def _send(self, payload: dict, status: int = 200, content_type: str = "application/json"):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _menu_text(payload: dict) -> str:
        """解析提示词 → 按约束随机拼菜单 → 返回 JSON 字符串。"""
        plan = parse_constraints(extract_prompt(payload))
        return json.dumps(
            build_menu(
                meal=plan["meal"],
                count=plan["count"],
                spicy_limit=plan["spicy"],
                avoid=plan["avoid"],
            ),
            ensure_ascii=False,
        )

    # ---------------- GET ----------------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/v1/models":
            self._send({"data": [{"id": "fake-chat"}, {"id": "fake-reasoner"}]})
        elif path == "/v1beta/models":
            self._send({"models": [{"name": "models/fake-gemini"}]})
        elif path == "/api/tags":
            self._send({"models": [{"name": "fake-qwen"}]})
        else:
            self._send({"error": {"message": f"假服务器没有这个路由：{path}"}}, status=404)

    # ---------------- POST ----------------
    def do_POST(self):
        path = self.path.split("?")[0]
        payload = self._body()
        # 餐次/菜数/辣度/忌口都从提示词里解析，见 _menu_text

        if path == "/v1/chat/completions":
            self._send(
                {
                    "id": "chatcmpl-fake",
                    "model": payload.get("model", "fake-chat"),
                    "choices": [
                        {"message": {"role": "assistant", "content": self._menu_text(payload)}},
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 200},
                }
            )
        elif path == "/v1/messages":
            self._send(
                {
                    "id": "msg_fake",
                    "model": payload.get("model", "fake-claude"),
                    "content": [{"type": "text", "text": self._menu_text(payload)}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 111, "output_tokens": 222},
                }
            )
        elif path.startswith("/v1beta/models/") and path.endswith(":generateContent"):
            self._send(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": self._menu_text(payload)}]}, "finishReason": "STOP"}
                    ],
                    "usageMetadata": {"promptTokenCount": 55, "candidatesTokenCount": 66},
                }
            )
        elif path == "/api/chat":
            self._send(
                {
                    "model": payload.get("model", "fake-qwen"),
                    "message": {"role": "assistant", "content": self._menu_text(payload)},
                    "prompt_eval_count": 7,
                    "eval_count": 9,
                }
            )
        else:
            self._send({"error": {"message": f"假服务器没有这个路由：{path}"}}, status=404)


def main() -> None:
    parser = argparse.ArgumentParser(description="本地假模型服务器（验证链路用）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=877)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    base = f"http://{args.host}:{args.port}"
    print("=" * 62)
    print("  🧪 本地假模型服务器已启动（不会真的调用任何大模型）")
    print(f"  监听: {base}")
    print("  OpenAI 兼容  → Base URL 填 " + base + "/v1")
    print("  Anthropic    → Base URL 填 " + base)
    print("  Ollama       → 地址    填 " + base)
    print("  Gemini       → Base URL 填 " + base)
    print("  模型名随便填，比如 fake-chat / fake-claude")
    print("  Ctrl+C 停止")
    print("=" * 62)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
