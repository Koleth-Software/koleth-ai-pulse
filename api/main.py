from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from contextlib import suppress
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
WEBSITE_DIR = ROOT / "website"
WEBSITE_INDEX = WEBSITE_DIR / "index.html"
WEBSITE_ASSETS = WEBSITE_DIR / "assets"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.env import load_env

load_env(ROOT / ".env")

from shared.db import (
    db_session,
    init_db,
    list_news,
    list_unsent_for_discord,
    mark_discord_sent,
    source_counts,
)
from shared.bot_config import load_bot_config, public_bot_config, save_bot_config
from shared.config import load_sources_config, remove_source, save_sources_config, upsert_source
from collector.collect import collect


LOGGER = logging.getLogger("koleth.api")


def get_allowed_origins() -> list[str]:
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "https://koleti.net.tr,https://www.koleti.net.tr,http://localhost:8000",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_db_path() -> str | None:
    explicit_db_path = os.getenv("DB_PATH", "").strip()
    if explicit_db_path:
        return explicit_db_path
    if os.getenv("DATABASE_URL", "").strip():
        return None
    if os.getenv("VERCEL"):
        raise RuntimeError("DATABASE_URL is required on Vercel")
    return "data/koleth-ai-pulse.db"


def ensure_db() -> None:
    with db_session(get_db_path()) as conn:
        init_db(conn)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def should_start_auto_collector() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("VERCEL"):
        return False
    return env_flag("API_COLLECTOR_ENABLED", default=False)


async def run_collection_once() -> None:
    result = await asyncio.to_thread(
        collect,
        get_config_path(),
        get_db_path(),
        workers=env_int("API_COLLECTOR_WORKERS", 8, minimum=1, maximum=24),
        limit_per_source=env_int("API_COLLECTOR_LIMIT_PER_SOURCE", 30, minimum=1, maximum=100),
    )
    LOGGER.info(
        "collector finished: sources=%s seen=%s inserted=%s errors=%s",
        result["sources"],
        result["seen"],
        result["inserted"],
        len(result["errors"]),
    )
    for source, error in result["errors"].items():
        LOGGER.warning("collector source failed: %s: %s", source, error)


async def auto_collector_loop() -> None:
    interval = env_int("COLLECTOR_INTERVAL_SECONDS", 3600, minimum=60)
    if env_flag("API_COLLECTOR_RUN_ON_START", default=True):
        try:
            await run_collection_once()
        except Exception:
            LOGGER.exception("initial collector run failed")

    while True:
        await asyncio.sleep(interval)
        try:
            await run_collection_once()
        except Exception:
            LOGGER.exception("scheduled collector run failed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        ensure_db()
    except Exception:
        LOGGER.exception("database initialization failed")
        if not os.getenv("VERCEL"):
            raise
    collector_task: asyncio.Task[None] | None = None
    if should_start_auto_collector():
        collector_task = asyncio.create_task(auto_collector_loop())
        LOGGER.info("automatic collector enabled")
    try:
        yield
    finally:
        if collector_task:
            collector_task.cancel()
            with suppress(asyncio.CancelledError):
                await collector_task


app = FastAPI(
    title="Koleth AI Pulse API",
    description="Local API for the Koleth AI Pulse collector, Discord bot and website.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

if WEBSITE_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=WEBSITE_ASSETS), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/ai-gundemi", include_in_schema=False)
@app.get("/panel", include_in_schema=False)
@app.get("/yonetim", include_in_schema=False)
def website() -> FileResponse:
    if not WEBSITE_INDEX.exists():
        raise HTTPException(status_code=404, detail="Web arayüzü bulunamadı")
    return FileResponse(WEBSITE_INDEX)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict[str, str]:
    try:
        ensure_db()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    backend = "postgres" if os.getenv("DATABASE_URL", "").strip() and not os.getenv("DB_PATH", "").strip() else "sqlite"
    return {"status": "ok", "backend": backend}


class SourcePayload(BaseModel):
    name: str = Field(min_length=1)
    type: str = "rss"
    url: str = Field(min_length=1)
    lang: str = Field(default="tr", min_length=2, max_length=8)
    category: str = "genel"


class KeywordsPayload(BaseModel):
    keywords_filter: list[str]


class BotSettingsPayload(BaseModel):
    enabled: bool = True
    discord_token: str | None = None
    channel_id: str = ""
    publish_language: str = ""
    publish_category: str = ""
    poll_seconds: int = Field(default=30, ge=5, le=3600)
    max_per_cycle: int = Field(default=10, ge=1, le=20)
    require_image: bool = False


def get_config_path() -> str:
    return os.getenv("SOURCES_CONFIG", "config/sources.yaml")


def get_bot_config_path() -> str:
    return os.getenv("BOT_CONFIG", "config/bot.yaml")


def config_or_400() -> dict[str, Any]:
    try:
        return load_sources_config(get_config_path())
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Konfigürasyon okunamadı: {exc}") from exc


def bot_config_or_400() -> dict[str, Any]:
    try:
        return load_bot_config(get_bot_config_path())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Bot ayarları okunamadı: {exc}") from exc


@app.get("/yonetim/config")
def yonetim_config() -> dict[str, Any]:
    return config_or_400()


@app.get("/yonetim/bot")
def yonetim_bot() -> dict[str, Any]:
    return public_bot_config(bot_config_or_400())


@app.put("/yonetim/bot")
def yonetim_bot_guncelle(payload: BotSettingsPayload) -> dict[str, Any]:
    current = bot_config_or_400()
    updated = current | payload.model_dump(exclude_none=True)
    if payload.discord_token is None or not payload.discord_token.strip():
        updated["discord_token"] = current.get("discord_token", "")
    try:
        saved = save_bot_config(updated, get_bot_config_path())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return public_bot_config(saved)


@app.post("/yonetim/kaynaklar")
def yonetim_kaynak_ekle(payload: SourcePayload) -> dict[str, Any]:
    config = config_or_400()
    try:
        upsert_source(config, payload.model_dump())
        save_sources_config(config, get_config_path())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return config


@app.put("/yonetim/kaynaklar/{source_name}")
def yonetim_kaynak_guncelle(source_name: str, payload: SourcePayload) -> dict[str, Any]:
    config = config_or_400()
    if not any(str(source.get("name", "")).casefold() == source_name.casefold() for source in config["sources"]):
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")
    try:
        upsert_source(config, payload.model_dump(), old_name=source_name)
        save_sources_config(config, get_config_path())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return config


@app.delete("/yonetim/kaynaklar/{source_name}")
def yonetim_kaynak_sil(source_name: str) -> dict[str, Any]:
    config = config_or_400()
    if not remove_source(config, source_name):
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")
    save_sources_config(config, get_config_path())
    return config


@app.put("/yonetim/keywords")
def yonetim_keywords(payload: KeywordsPayload) -> dict[str, Any]:
    config = config_or_400()
    keywords = [keyword.strip() for keyword in payload.keywords_filter if keyword.strip()]
    config["keywords_filter"] = list(dict.fromkeys(keywords))
    save_sources_config(config, get_config_path())
    return config


@app.post("/yonetim/topla")
def yonetim_topla(
    workers: int = Query(8, ge=1, le=24),
    limit_per_source: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    return collect(
        get_config_path(),
        get_db_path(),
        workers=workers,
        limit_per_source=limit_per_source,
    )


def validate_cron_authorization(authorization: str | None) -> None:
    secret = os.getenv("CRON_SECRET", "").strip()
    if secret and authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Geçersiz cron yetkisi")


@app.get("/cron/collect")
@app.get("/api/cron/collect")
def cron_collect(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    validate_cron_authorization(authorization)
    return collect(
        get_config_path(),
        get_db_path(),
        workers=env_int("API_COLLECTOR_WORKERS", 8, minimum=1, maximum=24),
        limit_per_source=env_int("API_COLLECTOR_LIMIT_PER_SOURCE", 30, minimum=1, maximum=100),
    )


@app.get("/haberler")
def haberler(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kaynak: str | None = None,
    kategori: str | None = None,
    dil: str | None = None,
) -> list[dict[str, Any]]:
    with db_session(get_db_path()) as conn:
        init_db(conn)
        return list_news(
            conn,
            limit=limit,
            offset=offset,
            kaynak=kaynak,
            kategori=kategori,
            dil=dil,
        )


@app.get("/haberler/yeni")
def haberler_yeni(
    limit: int = Query(20, ge=1, le=100),
    dil: str | None = None,
    kategori: str | None = None,
    gorselli: bool = False,
) -> list[dict[str, Any]]:
    with db_session(get_db_path()) as conn:
        init_db(conn)
        return list_unsent_for_discord(
            conn,
            limit=limit,
            dil=dil,
            kategori=kategori,
            require_image=gorselli,
        )


@app.post("/haberler/{haber_id}/gonderildi")
def haber_gonderildi(haber_id: int) -> dict[str, Any]:
    with db_session(get_db_path()) as conn:
        init_db(conn)
        if not mark_discord_sent(conn, haber_id):
            raise HTTPException(status_code=404, detail="Haber bulunamadı")
    return {"id": haber_id, "discord_gonderildi": True}


@app.get("/kaynaklar")
def kaynaklar() -> list[dict[str, Any]]:
    with db_session(get_db_path()) as conn:
        init_db(conn)
        return source_counts(conn)
