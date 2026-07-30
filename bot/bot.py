from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.env import load_env

load_env(ROOT / ".env")

from shared.bot_config import load_bot_config

LOGGER = logging.getLogger("koleth.bot")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_AUTH_TOKEN = (
    os.getenv("API_AUTH_TOKEN", "").strip()
    or os.getenv("BOT_API_TOKEN", "").strip()
    or os.getenv("ADMIN_TOKEN", "").strip()
)
POLL_SECONDS = int(os.getenv("BOT_POLL_SECONDS", "30"))
MAX_DESCRIPTION = 280
DISPLAY_TIMEZONE = timezone(timedelta(minutes=int(os.getenv("DISPLAY_UTC_OFFSET_MINUTES", "180"))))
TURKISH_MONTHS = (
    "",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)
LANGUAGE_FLAGS = {
    "tr": "🇹🇷",
    "en": "🇬🇧",
}


class KolethPulseBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        register_commands(self)
        await self.tree.sync()
        publish_new_items.start(self)

    async def close(self) -> None:
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        LOGGER.info("logged in as %s", self.user)


def api_headers() -> dict[str, str]:
    if not API_AUTH_TOKEN:
        return {}
    return {"Authorization": f"Bearer {API_AUTH_TOKEN}"}


async def api_get(client: KolethPulseBot, path: str, **params: Any) -> Any:
    if not client.session:
        raise RuntimeError("HTTP session is not ready")
    async with client.session.get(f"{API_BASE_URL}{path}", params=params, headers=api_headers()) as response:
        response.raise_for_status()
        return await response.json()


async def api_post(client: KolethPulseBot, path: str) -> Any:
    if not client.session:
        raise RuntimeError("HTTP session is not ready")
    async with client.session.post(f"{API_BASE_URL}{path}", headers=api_headers()) as response:
        response.raise_for_status()
        return await response.json()


def current_bot_settings() -> dict[str, Any]:
    return load_bot_config(os.getenv("BOT_CONFIG", "config/bot.yaml"))


def parse_channel_id(value: str | None) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def format_description(item: dict[str, Any]) -> str:
    summary = item.get("ozet") or ""
    if len(summary) > MAX_DESCRIPTION:
        summary = summary[: MAX_DESCRIPTION - 1].rstrip() + "…"
    meta = f"{item.get('kaynak', 'Kaynak')} · {item.get('kategori', 'genel')}"
    return f"{summary}\n\n{meta}" if summary else meta


def language_flag(value: str | None) -> str:
    if not value:
        return "🌐"
    return LANGUAGE_FLAGS.get(value.casefold(), value.upper())


def format_datetime_label(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local_time = parsed.astimezone(DISPLAY_TIMEZONE)
    month = TURKISH_MONTHS[local_time.month]
    return f"{local_time.day} {month} {local_time.year} {local_time.hour:02d}:{local_time.minute:02d}"


def make_embed(item: dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=item["baslik"][:256],
        url=item["link"],
        description=format_description(item),
        color=discord.Color.from_rgb(20, 120, 88),
    )
    embed.set_footer(text="Koleth AI Pulse")
    if item.get("image_url"):
        embed.set_image(url=item["image_url"])
    published_label = format_datetime_label(item.get("yayin_tarihi") or item.get("eklenme_tarihi"))
    if published_label:
        embed.add_field(name="Yayın", value=published_label, inline=True)
    if item.get("dil"):
        embed.add_field(name="Dil", value=language_flag(item.get("dil")), inline=True)
    return embed


@tasks.loop(seconds=POLL_SECONDS)
async def publish_new_items(client: KolethPulseBot) -> None:
    settings = current_bot_settings()
    publish_new_items.change_interval(seconds=settings["poll_seconds"])

    if not settings["enabled"]:
        LOGGER.info("bot publishing is disabled")
        return

    channel_id = parse_channel_id(settings.get("channel_id"))
    if not channel_id:
        LOGGER.warning("DISCORD_CHANNEL_ID is missing; skipping publish cycle")
        return

    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
    if not hasattr(channel, "send"):
        LOGGER.warning("channel %s is not a sendable channel", channel_id)
        return

    params: dict[str, Any] = {"limit": settings["max_per_cycle"]}
    if settings.get("publish_language"):
        params["dil"] = settings["publish_language"]
    if settings.get("publish_category"):
        params["kategori"] = settings["publish_category"]
    if settings.get("require_image"):
        params["gorselli"] = True

    try:
        items = await api_get(client, "/haberler/yeni", **params)
    except Exception:
        LOGGER.exception("failed to fetch new items")
        return

    for item in items:
        try:
            await channel.send(embed=make_embed(item))
            await api_post(client, f"/haberler/{item['id']}/gonderildi")
            await asyncio.sleep(1)
        except Exception:
            LOGGER.exception("failed to publish item %s", item.get("id"))


@publish_new_items.before_loop
async def before_publish_new_items() -> None:
    await asyncio.sleep(5)


def register_commands(client: KolethPulseBot) -> None:
    @client.tree.command(name="haberler", description="Son AI haberlerini gösterir")
    @app_commands.describe(kaynak="İsteğe bağlı kaynak adı", kategori="ai, research, community veya genel")
    async def haberler(
        interaction: discord.Interaction,
        kaynak: str | None = None,
        kategori: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            items = await api_get(client, "/haberler", limit=5, kaynak=kaynak, kategori=kategori)
        except Exception:
            LOGGER.exception("slash command /haberler failed")
            await interaction.followup.send("Haberler alınamadı.", ephemeral=True)
            return

        if not items:
            await interaction.followup.send("Bu filtrelerle haber bulunamadı.", ephemeral=True)
            return
        await interaction.followup.send(embeds=[make_embed(item) for item in items], ephemeral=True)

    @client.tree.command(name="kaynaklar", description="Kaynak bazında haber sayılarını gösterir")
    async def kaynaklar(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await api_get(client, "/kaynaklar")
        except Exception:
            LOGGER.exception("slash command /kaynaklar failed")
            await interaction.followup.send("Kaynaklar alınamadı.", ephemeral=True)
            return

        if not rows:
            await interaction.followup.send("Henüz haber yok.", ephemeral=True)
            return
        lines = [
            f"**{row['kaynak']}** · {row['kategori']} · {language_flag(row.get('dil'))}: {row['haber_sayisi']}"
            for row in rows[:20]
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    token = current_bot_settings().get("discord_token", "")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required")
    KolethPulseBot().run(token)


if __name__ == "__main__":
    main()
