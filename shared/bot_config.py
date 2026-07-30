from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_BOT_CONFIG_PATH = Path("config/bot.yaml")
LANGUAGE_VALUES = {"", "tr", "en"}
CATEGORY_VALUES = {"", "ai", "research", "community", "genel"}
SETTINGS_NAMESPACE = "bot"


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def coerce_int(value: Any, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def resolve_bot_config_path(path: str | os.PathLike[str] | None = None) -> Path:
    return Path(path) if path else Path(os.getenv("BOT_CONFIG", str(DEFAULT_BOT_CONFIG_PATH)))


def uses_database_backend() -> bool:
    backend = os.getenv("BOT_CONFIG_BACKEND", "auto").strip().lower()
    if backend in {"db", "database", "postgres"}:
        return True
    if backend in {"file", "yaml"}:
        return False
    return bool(os.getenv("DATABASE_URL", "").strip())


def default_bot_config() -> dict[str, Any]:
    return {
        "enabled": env_bool("BOT_ENABLED", True),
        "discord_token": os.getenv("DISCORD_TOKEN", ""),
        "channel_id": os.getenv("DISCORD_CHANNEL_ID", ""),
        "publish_language": os.getenv("BOT_PUBLISH_LANGUAGE", "").strip().lower(),
        "publish_category": os.getenv("BOT_PUBLISH_CATEGORY", "").strip().lower(),
        "poll_seconds": env_int("BOT_POLL_SECONDS", 30, minimum=5, maximum=3600),
        "max_per_cycle": env_int("BOT_MAX_PER_CYCLE", 10, minimum=1, maximum=20),
        "require_image": env_bool("BOT_REQUIRE_IMAGE", False),
    }


def normalize_bot_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = default_bot_config()
    normalized.update(config or {})

    normalized["enabled"] = coerce_bool(normalized.get("enabled"), True)
    normalized["discord_token"] = str(normalized.get("discord_token", "")).strip()
    normalized["channel_id"] = str(normalized.get("channel_id", "")).strip()

    language = str(normalized.get("publish_language", "")).strip().lower()
    if language not in LANGUAGE_VALUES:
        raise ValueError("Gönderim dili tr, en veya boş olmalı")
    normalized["publish_language"] = language

    category = str(normalized.get("publish_category", "")).strip().lower()
    if category not in CATEGORY_VALUES:
        raise ValueError("Kategori ai, research, community, genel veya boş olmalı")
    normalized["publish_category"] = category

    normalized["poll_seconds"] = coerce_int(normalized.get("poll_seconds"), 30, minimum=5, maximum=3600)
    normalized["max_per_cycle"] = coerce_int(normalized.get("max_per_cycle"), 10, minimum=1, maximum=20)
    normalized["require_image"] = coerce_bool(normalized.get("require_image"), False)
    return normalized


def load_bot_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    if uses_database_backend():
        from shared.db import db_session, init_db, load_settings

        with db_session() as conn:
            init_db(conn)
            return normalize_bot_config(load_settings(conn, SETTINGS_NAMESPACE))

    config_path = resolve_bot_config_path(path)
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            file_config = yaml.safe_load(handle) or {}
    else:
        file_config = {}
    return normalize_bot_config(file_config)


def save_bot_config(config: dict[str, Any], path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    normalized = normalize_bot_config(config)
    if uses_database_backend():
        from shared.db import db_session, init_db, save_settings

        with db_session() as conn:
            init_db(conn)
            save_settings(conn, SETTINGS_NAMESPACE, normalized)
        return normalized

    config_path = resolve_bot_config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            normalized,
            handle,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
    return normalized


def public_bot_config(config: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in config.items() if key != "discord_token"}
    token = str(config.get("discord_token", ""))
    public["token_set"] = bool(token)
    public["token_mask"] = f"{token[:6]}...{token[-4:]}" if len(token) >= 12 else ""
    return public
