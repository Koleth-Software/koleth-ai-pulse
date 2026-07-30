from __future__ import annotations

import argparse
import html
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.env import load_env

load_env(ROOT / ".env")

from shared.config import load_sources_config
from shared.db import NewsItem, db_session, init_db, insert_news


LOGGER = logging.getLogger("koleth.collector")
USER_AGENT = "KolethAIPulse/0.1 (+https://koleti.net.tr)"
TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[\w#+.-]+", re.UNICODE)


def load_config(path: str | Path) -> dict[str, Any]:
    return load_sources_config(path)


def clean_text(value: str | None, *, max_length: int | None = None) -> str | None:
    if not value:
        return None
    text = TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = SPACE_RE.sub(" ", text).strip()
    if max_length and len(text) > max_length:
        return text[: max_length - 1].rstrip() + "…"
    return text


def parse_date(entry: Any) -> str | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    parsed_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_struct:
        return datetime(*parsed_struct[:6], tzinfo=timezone.utc).isoformat()
    return None


def normalize_image_url(value: str | None) -> str | None:
    if not value:
        return None
    url = html.unescape(str(value).strip())
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith(("http://", "https://")):
        return url
    return None


def extract_image_url(entry: Any) -> str | None:
    candidates: list[str | None] = []

    for key in ("media_thumbnail", "media_content"):
        for media in entry.get(key, []) or []:
            if isinstance(media, dict):
                candidates.append(media.get("url"))

    for link in entry.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        link_type = str(link.get("type", ""))
        rel = str(link.get("rel", ""))
        if link_type.startswith("image/") or rel in {"enclosure", "image"}:
            candidates.append(link.get("href"))

    for key in ("summary", "description", "content"):
        value = entry.get(key)
        if isinstance(value, list):
            for part in value:
                if isinstance(part, dict):
                    match = IMG_RE.search(str(part.get("value", "")))
                    if match:
                        candidates.append(match.group(1))
        else:
            match = IMG_RE.search(str(value or ""))
            if match:
                candidates.append(match.group(1))

    for candidate in candidates:
        url = normalize_image_url(candidate)
        if url:
            return url
    return None


def should_keep(source: dict[str, Any], title: str, summary: str | None, keywords: list[str]) -> bool:
    if source.get("category") != "genel":
        return True
    haystack = f"{title} {summary or ''}".casefold()
    tokens = set(WORD_RE.findall(haystack))
    for keyword in keywords:
        folded = keyword.casefold().strip()
        if not folded:
            continue
        if len(folded) <= 3 and SPACE_RE.search(folded) is None:
            if folded in tokens:
                return True
            continue
        if folded in haystack:
            return True
    return False


def fetch_source(source: dict[str, Any], keywords: list[str], limit_per_source: int) -> tuple[str, list[NewsItem], str | None]:
    if source.get("type") != "rss":
        return source.get("name", "unknown"), [], "unsupported source type"

    name = source["name"]
    try:
        response = requests.get(
            source["url"],
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return name, [], str(exc)

    parsed = feedparser.parse(response.content)
    if parsed.bozo and parsed.bozo_exception:
        LOGGER.warning("%s feed parse warning: %s", name, parsed.bozo_exception)

    items: list[NewsItem] = []
    for entry in parsed.entries[:limit_per_source]:
        title = clean_text(entry.get("title")) or ""
        link = entry.get("link")
        if not title or not link:
            continue

        summary = clean_text(entry.get("summary") or entry.get("description"), max_length=900)
        if not should_keep(source, title, summary, keywords):
            continue

        items.append(
            NewsItem(
                kaynak=name,
                kategori=source.get("category", "genel"),
                dil=source.get("lang", "tr"),
                baslik=title,
                ozet=summary,
                link=link,
                image_url=extract_image_url(entry),
                yayin_tarihi=parse_date(entry),
            )
        )

    return name, items, None


def collect(config_path: str | Path, db_path: str | Path | None = None, *, workers: int = 8, limit_per_source: int = 30) -> dict[str, Any]:
    config = load_config(config_path)
    sources = config["sources"]
    keywords = config["keywords_filter"]

    inserted = 0
    seen = 0
    errors: dict[str, str] = {}

    with db_session(db_path) as conn:
        init_db(conn)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [
                executor.submit(fetch_source, source, keywords, limit_per_source)
                for source in sources
            ]
            for future in as_completed(futures):
                name, items, error = future.result()
                if error:
                    errors[name] = error
                    continue
                seen += len(items)
                for item in items:
                    if insert_news(conn, item):
                        inserted += 1

    return {"sources": len(sources), "seen": seen, "inserted": inserted, "errors": errors}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Koleth AI Pulse RSS collector")
    parser.add_argument("--config", default="config/sources.yaml", help="sources.yaml path")
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--workers", type=int, default=8, help="parallel fetch worker count")
    parser.add_argument("--limit-per-source", type=int, default=30, help="maximum entries to read per source")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    result = collect(args.config, args.db, workers=args.workers, limit_per_source=args.limit_per_source)
    LOGGER.info(
        "collection finished: sources=%s seen=%s inserted=%s errors=%s",
        result["sources"],
        result["seen"],
        result["inserted"],
        len(result["errors"]),
    )
    for source, error in result["errors"].items():
        LOGGER.warning("%s failed: %s", source, error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
