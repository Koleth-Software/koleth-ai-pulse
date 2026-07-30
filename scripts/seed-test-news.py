from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.db import NewsItem, db_session, init_db, insert_news
from shared.env import load_env


def main() -> int:
    load_env(ROOT / ".env")
    import os

    db_path = os.getenv("DB_PATH", "data/koleth-ai-pulse.db")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    item = NewsItem(
        kaynak="Koleth Test",
        kategori="ai",
        dil="tr",
        baslik=f"Koleth AI Pulse Discord test mesajı {stamp}",
        ozet="Bu kayıt yerel bot testinden üretildi. Discord'a gönderildikten sonra işaretlenecek.",
        link=f"https://example.test/koleth-discord-test/{stamp}",
        image_url=f"https://picsum.photos/seed/koleth-{stamp}/1200/675",
        yayin_tarihi=datetime.now(timezone.utc).isoformat(),
    )

    with db_session(db_path) as conn:
        init_db(conn)
        conn.execute(
            "UPDATE haberler SET discord_gonderildi = 1 WHERE kaynak = ? AND discord_gonderildi = 0",
            ("Koleth Test",),
        )
        conn.commit()
        inserted = insert_news(conn, item)

    if inserted:
        print(f"Inserted test news: {item.baslik}")
    else:
        print("Test news already exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
