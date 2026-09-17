#!/usr/bin/env python
"""吃什么？本地/容器统一启动入口。

    python run.py

等价于： uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"🍚 {settings.app_name} 启动中 → http://{settings.host}:{settings.port}")
    print(f"   数据目录: {settings.data_dir}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    main()
