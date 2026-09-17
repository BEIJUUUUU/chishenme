"""定时任务：到点生成菜单并推送到微信。

用 APScheduler BackgroundScheduler + 独立 asyncio 事件循环。
修改配置后调用 `reload()` 热更新任务时间，不需要重启容器。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .core.generator import generate_day
from .db import session_scope
from .runtime_config import AppConfig, load_config
from .services import push_day

log = logging.getLogger("chishenme.scheduler")

JOB_LUNCH = "daily-lunch"
JOB_DINNER = "daily-dinner"


def parse_hhmm(value: str, fallback: tuple[int, int]) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.strip().split(":")
        hour, minute = int(hour_text), int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except Exception:
        pass
    return fallback


class PlanScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.tz = ZoneInfo(self.settings.timezone)
        self._scheduler: BackgroundScheduler | None = None

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._scheduler is not None:
            return
        self._scheduler = BackgroundScheduler(timezone=self.tz, daemon=True)
        self._scheduler.start()
        with session_scope() as db:
            config = load_config(db)
        self.reload(config)
        log.info("调度器已启动，时区 %s", self.settings.timezone)

    def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def reload(self, config: AppConfig) -> None:
        if self._scheduler is None:
            return
        for job_id in (JOB_LUNCH, JOB_DINNER):
            existing = self._scheduler.get_job(job_id)
            if existing:
                self._scheduler.remove_job(job_id)

        if not config.scheduler_enabled:
            log.info("定时任务已关闭")
            return

        lunch_h, lunch_m = parse_hhmm(config.lunch_push_time, (7, 30))
        dinner_h, dinner_m = parse_hhmm(config.dinner_push_time, (15, 30))

        self._scheduler.add_job(
            self._run_lunch,
            CronTrigger(hour=lunch_h, minute=lunch_m, timezone=self.tz),
            id=JOB_LUNCH,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.add_job(
            self._run_dinner,
            CronTrigger(hour=dinner_h, minute=dinner_m, timezone=self.tz),
            id=JOB_DINNER,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        log.info("定时任务：午餐 %02d:%02d / 晚餐 %02d:%02d", lunch_h, lunch_m, dinner_h, dinner_m)

    def jobs(self) -> list[dict]:
        if self._scheduler is None:
            return []
        return [
            {
                "id": job.id,
                "next_run": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "",
            }
            for job in self._scheduler.get_jobs()
        ]

    def run_now(self, meal: str) -> None:
        """手动触发一次（异步执行，不阻塞请求）。"""
        target = self._run_lunch if meal == "午餐" else self._run_dinner
        asyncio.run(target())

    # ------------------------------------------------------------------ 任务体
    async def _run_lunch(self) -> None:
        await self._run_window("午餐")

    async def _run_dinner(self) -> None:
        await self._run_window("晚餐")

    async def _run_window(self, meal: str) -> None:
        try:
            with session_scope() as db:
                config = load_config(db)
                days_ahead = max(0, config.push_days_ahead)
                target = date.today() + timedelta(days=days_ahead)
                # 提前播报时一次给出全天两餐，方便一次性买菜
                meals: tuple[str, ...] = ("午餐", "晚餐") if days_ahead > 0 else (meal,)

                log.info("开始生成 %s %s 的菜单", target, meals)
                await generate_day(db, config, target, meals=meals)

                results = await push_day(db, config, target, meals=meals)
                ok = sum(1 for r in results if r["ok"])
                log.info("推送完成：%s/%s 成功", ok, len(results))
                for result in results:
                    if not result["ok"]:
                        log.warning("通道 %s 推送失败：%s", result["channel"], result["message"])
        except Exception:
            log.exception("定时任务执行失败（%s）", meal)


scheduler = PlanScheduler()
