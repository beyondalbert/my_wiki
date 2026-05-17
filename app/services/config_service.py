"""System config service: read / write runtime settings (DB-backed, cached).

Exposes get_config(key) / set_config(key, value) for use by other services.
Values are cached in-process to avoid per-request DB queries; cache is
invalidated on write.
"""
from __future__ import annotations

import threading

from ..extensions import db
from ..models import SystemConfig


_cache: dict[str, str] = {}
_cache_loaded = False
_lock = threading.Lock()


def _ensure_cache() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    with _lock:
        if _cache_loaded:
            return
        rows = SystemConfig.query.all()
        for r in rows:
            _cache[r.key] = r.value or ""
        _cache_loaded = True


def invalidate_cache() -> None:
    global _cache_loaded
    with _lock:
        _cache.clear()
        _cache_loaded = False


def get(key: str, default: str = "") -> str:
    """Get a config value by key. Returns default if not set."""
    _ensure_cache()
    return _cache.get(key, default)


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def set_config(key: str, value: str, description: str | None = None) -> None:
    """Set a config value. Creates the row if not exists."""
    row = db.session.get(SystemConfig, key)
    if row is None:
        row = SystemConfig(key=key, value=value, description=description or "")
        db.session.add(row)
    else:
        row.value = value
        if description is not None:
            row.description = description
    db.session.commit()
    # 立刻更新缓存
    _cache[key] = value


def get_all() -> dict[str, str]:
    """Return all config as dict."""
    _ensure_cache()
    return dict(_cache)


# 预定义的 AI 相关配置 key（方便 admin UI 展示）
AI_CONFIG_KEYS = [
    {"key": "OPENAI_BASE_URL", "label": "API 接口地址", "placeholder": "https://api.openai.com/v1", "type": "text"},
    {"key": "OPENAI_API_KEY", "label": "API 密钥", "placeholder": "sk-...", "type": "password"},
    {"key": "CHAT_MODEL", "label": "对话模型", "placeholder": "gpt-4o-mini", "type": "text"},
    {"key": "EMBEDDING_MODEL", "label": "嵌入模型", "placeholder": "text-embedding-3-small", "type": "text"},
    {"key": "ENABLE_RAG", "label": "启用向量检索 (RAG)", "placeholder": "false", "type": "toggle"},
]
