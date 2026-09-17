"""从 LLM 返回文本里稳健地抠出 JSON。

LLM 常见骚操作：```json 包裹、前后加解释、结尾多个逗号、中文全角引号。
这里逐层降级处理，抠不出来就抛 ValueError 交给上层重试。
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _iter_balanced(text: str) -> list[str]:
    """扫描所有平衡的 {...} 片段（考虑字符串内的括号）。"""
    chunks: list[str] = []
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    chunks.append(text[start : i + 1])
                    start = -1
    return chunks


def _clean(fragment: str) -> str:
    fragment = fragment.strip()
    fragment = fragment.replace("，", ",").replace("：", ":")
    # 去掉尾随逗号
    fragment = re.sub(r",\s*([}\]])", r"\1", fragment)
    # 中文引号 → 英文引号（只处理非内容位置的常见错误：键名）
    fragment = re.sub(r"([{,]\s*)“([^”]+)”(\s*:)", r'\1"\2"\3', fragment)
    return fragment


def extract_json(text: str) -> dict[str, Any]:
    """尽最大努力把文本解析为 dict。"""
    if not text or not text.strip():
        raise ValueError("LLM 返回为空")

    candidates: list[str] = []
    candidates.extend(_FENCE_RE.findall(text))
    candidates.extend(_iter_balanced(text))
    candidates.append(text)

    errors: list[str] = []
    for candidate in candidates:
        for attempt in (candidate, _clean(candidate)):
            try:
                data = json.loads(attempt)
            except (json.JSONDecodeError, TypeError) as exc:
                errors.append(str(exc))
                continue
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                # 允许 LLM 直接返回数组
                return {"meals": data}
    raise ValueError(f"无法从返回内容解析出 JSON：{errors[-1] if errors else '未知错误'}")


def coerce_str_list(value: Any) -> list[str]:
    """把 LLM 可能给出的 str / list / None 统一成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，、;；/\n]+", value)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("ingredient")
                if isinstance(name, str) and name.strip():
                    out.append(name.strip())
        return out
    return [str(value)]
