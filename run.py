#!/usr/bin/env python
"""吃什么？本地/容器统一启动入口。

    python run.py

等价于： uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import contextlib
import os
import sys

import uvicorn

from app.config import get_settings


def set_console_title(title: str) -> None:
    """Windows 下把控制台窗口标题改掉，方便「停止.bat」和用户辨认。"""
    if os.name == "nt":
        with contextlib.suppress(Exception):  # 无控制台（比如被 service 拉起）时忽略
            os.system(f"title {title}")


def main() -> None:
    settings = get_settings()
    set_console_title(f"{settings.app_name} 服务")
    print("=" * 52)
    print(f"  🍚 {settings.app_name} 正在启动 ...")
    print(f"  访问地址: http://127.0.0.1:{settings.port}/")
    print(f"  默认账号: {settings.admin_user} / {settings.admin_password}")
    print(f"  数据目录: {settings.data_dir}")
    print("=" * 52)
    print("  停止服务：双击 停止.bat，或直接关闭本窗口")
    print()

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.host,
            port=settings.port,
            reload=settings.debug,
            log_level="debug" if settings.debug else "info",
        )
    except KeyboardInterrupt:  # pragma: no cover
        print("\n已停止。")
    except OSError as exc:
        print(f"\n[错误] 启动失败：{exc}")
        print(f"端口 {settings.port} 可能被占用，可以换个端口：set CSM_PORT=8081")
        sys.exit(1)


if __name__ == "__main__":
    main()
