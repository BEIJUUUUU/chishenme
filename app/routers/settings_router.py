"""设置页：数据驱动的配置表单。"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..deps import AppConfigDep, CurrentUser, DbSession
from ..notify import NOTIFIERS
from ..runtime_config import SETTINGS_SCHEMA, AppConfig, field_map, save_config
from ..scheduler import scheduler
from ..security import hash_password, verify_password
from ..web import render

router = APIRouter(tags=["settings"])


def _split_tags(raw: str) -> list[str]:
    text = (raw or "").replace("，", ",").replace("、", ",").replace(";", ",").replace("；", ",")
    parts: list[str] = []
    for line in text.split("\n"):
        for chunk in line.split(","):
            item = chunk.strip()
            if item and item not in parts:
                parts.append(item)
    return parts


def parse_form(form, config: AppConfig) -> dict:
    """按字段类型解析表单，返回可直接喂给 AppConfig 的 dict。"""
    updates: dict = {}
    for key, spec in field_map().items():
        ftype = spec.get("type", "text")
        if ftype == "bool":
            updates[key] = form.get(key) is not None
        elif ftype in ("checkboxes",):
            updates[key] = [v for v in form.getlist(key) if str(v).strip()]
        elif ftype == "tags":
            updates[key] = _split_tags(str(form.get(key) or ""))
        elif ftype == "password":
            raw = str(form.get(key) or "").strip()
            # 密码类留空表示「不修改」，避免误清空
            updates[key] = raw if raw else getattr(config, key)
        elif ftype in ("number", "float"):
            raw = str(form.get(key) or "").strip()
            if raw == "":
                continue
            updates[key] = float(raw) if ftype == "float" else int(float(raw))
        else:
            raw = str(form.get(key) or "").strip()
            if raw == "" and ftype == "select":
                continue
            updates[key] = raw
    return updates


@router.get("/settings")
def settings_page(request: Request, db: DbSession, user: CurrentUser, config: AppConfigDep, tab: str = "family"):
    notifiers = [
        {
            "key": key,
            "label": notifier.label,
            "configured": notifier.configured(config),
            "mask": notifier.mask(config),
            "doc": notifier.doc,
        }
        for key, notifier in NOTIFIERS.items()
    ]
    return render(
        request,
        "settings.html",
        user=user,
        config=config,
        schema=SETTINGS_SCHEMA,
        notifiers=notifiers,
        jobs=scheduler.jobs(),
        scheduler_running=scheduler.running,
        tab=tab,
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    config: AppConfigDep,
):
    form = await request.form()
    updates = parse_form(form, config)
    merged = config.model_dump()
    merged.update(updates)

    try:
        new_config = AppConfig(**merged)
    except Exception as exc:
        return RedirectResponse(f"/settings?msg=保存失败：{exc}&level=error", status_code=303)

    save_config(db, new_config)
    scheduler.reload(new_config)

    validation = validate_config(new_config)
    if validation:
        return RedirectResponse(
            f"/settings?msg=已保存，但请注意：{'；'.join(validation)}&level=warn", status_code=303
        )
    return RedirectResponse("/settings?msg=设置已保存 ✅&level=ok", status_code=303)


def validate_config(config: AppConfig) -> list[str]:
    notes: list[str] = []
    if config.llm_mode == "openai" and not config.openai_api_key:
        notes.append("选了 OpenAI 兼容通道但没填 API Key，会自动退回本地菜谱库")
    if config.llm_mode == "ollama" and not config.ollama_base_url:
        notes.append("选了本地 Ollama 但没填地址，会自动退回本地菜谱库")
    if not config.push_channels:
        if config.scheduler_enabled:
            notes.append("启用了定时任务但没有选择推送通道，菜单不会发到微信")
        else:
            notes.append("没有启用任何推送通道，暂时只能手动在网页上看菜单")
    return notes


@router.post("/settings/password")
def change_password(
    db: DbSession,
    user: CurrentUser,
    old_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    if not verify_password(old_password, user.password_hash):
        return RedirectResponse("/settings?msg=原密码不正确&level=error", status_code=303)
    if len(new_password) < 6:
        return RedirectResponse("/settings?msg=新密码至少 6 位&level=error", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse("/settings?msg=两次输入的新密码不一致&level=error", status_code=303)
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/settings?msg=密码已更新 ✅&level=ok", status_code=303)


@router.post("/settings/reset-library")
def reset_library(db: DbSession, user: CurrentUser):
    from ..core.pantry import seed_database

    added = seed_database(db, force=False)
    return RedirectResponse(f"/dishes?msg=内置菜谱已同步，新增 {added} 道&level=ok", status_code=303)
