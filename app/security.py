"""密码哈希与签名 Cookie 会话（零外部依赖，只用标准库 + itsdangerous）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 240_000


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="csm-session")


def encode_session(payload: dict[str, Any]) -> str:
    return _serializer().dumps(payload)


def decode_session(token: str) -> dict[str, Any] | None:
    try:
        return _serializer().loads(token, max_age=get_settings().session_max_age)
    except (BadSignature, SignatureExpired, Exception):
        return None
