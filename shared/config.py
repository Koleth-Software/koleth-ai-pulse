from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config/sources.yaml")
SOURCE_CATEGORIES = {"ai", "research", "community", "genel"}
SETTINGS_NAMESPACE = "sources_config"


def resolve_config_path(path: str | os.PathLike[str] | None = None) -> Path:
    return Path(path) if path else Path(os.getenv("SOURCES_CONFIG", str(DEFAULT_CONFIG_PATH)))


def uses_database_backend() -> bool:
    backend = os.getenv("SOURCES_CONFIG_BACKEND", "auto").strip().lower()
    if backend in {"db", "database", "postgres"}:
        return True
    if backend in {"file", "yaml"}:
        return False
    return bool(os.getenv("DATABASE_URL", "").strip())


def load_sources_config_file(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    config_path = resolve_config_path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    config.setdefault("sources", [])
    config.setdefault("keywords_filter", [])
    return config


def load_sources_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    if uses_database_backend():
        from shared.db import db_session, init_db, load_settings, save_settings

        with db_session() as conn:
            init_db(conn)
            config = load_settings(conn, SETTINGS_NAMESPACE)
            if not config:
                config = load_sources_config_file(path)
                save_settings(conn, SETTINGS_NAMESPACE, config)
            config.setdefault("sources", [])
            config.setdefault("keywords_filter", [])
            return config

    config = load_sources_config_file(path)
    config.setdefault("sources", [])
    config.setdefault("keywords_filter", [])
    return config


def save_sources_config(config: dict[str, Any], path: str | os.PathLike[str] | None = None) -> None:
    if uses_database_backend():
        from shared.db import db_session, init_db, save_settings

        with db_session() as conn:
            init_db(conn)
            save_settings(
                conn,
                SETTINGS_NAMESPACE,
                {
                    "sources": config.get("sources", []),
                    "keywords_filter": config.get("keywords_filter", []),
                },
            )
        return

    config_path = resolve_config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            config,
            handle,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )


def normalize_source(source: dict[str, Any]) -> dict[str, str]:
    normalized = {
        "name": str(source.get("name", "")).strip(),
        "type": str(source.get("type", "rss")).strip() or "rss",
        "url": str(source.get("url", "")).strip(),
        "lang": str(source.get("lang", "tr")).strip().lower() or "tr",
        "category": str(source.get("category", "genel")).strip().lower() or "genel",
    }
    validate_source(normalized)
    return normalized


def validate_source(source: dict[str, Any]) -> None:
    if not source.get("name"):
        raise ValueError("Kaynak adı boş olamaz")
    if source.get("type") != "rss":
        raise ValueError("Şimdilik sadece rss kaynak tipi destekleniyor")
    if not str(source.get("url", "")).startswith(("http://", "https://")):
        raise ValueError("RSS adresi http:// veya https:// ile başlamalı")
    if source.get("category") not in SOURCE_CATEGORIES:
        raise ValueError("Kategori ai, research, community veya genel olmalı")


def upsert_source(config: dict[str, Any], source: dict[str, Any], old_name: str | None = None) -> dict[str, Any]:
    normalized = normalize_source(source)
    old_name_folded = old_name.casefold() if old_name else normalized["name"].casefold()
    replaced = False

    for index, existing in enumerate(config["sources"]):
        existing_name = str(existing.get("name", "")).casefold()
        existing_url = str(existing.get("url", "")).casefold()
        if existing_name == old_name_folded:
            config["sources"][index] = normalized
            replaced = True
            continue
        if existing_url == normalized["url"].casefold():
            raise ValueError("Bu RSS adresi zaten tanımlı")

    if not replaced:
        if any(str(existing.get("name", "")).casefold() == normalized["name"].casefold() for existing in config["sources"]):
            raise ValueError("Bu kaynak adı zaten tanımlı")
        config["sources"].append(normalized)

    return config


def remove_source(config: dict[str, Any], source_name: str) -> bool:
    before = len(config["sources"])
    config["sources"] = [
        source
        for source in config["sources"]
        if str(source.get("name", "")).casefold() != source_name.casefold()
    ]
    return len(config["sources"]) != before
