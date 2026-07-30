from shared.db import (
    NewsItem,
    connect,
    init_db,
    insert_news,
    list_news,
    list_unsent_for_discord,
    mark_discord_sent,
    source_counts,
)


def test_insert_news_ignores_duplicate_links(tmp_path):
    db_path = tmp_path / "pulse.db"
    item = NewsItem(
        kaynak="Test Feed",
        kategori="ai",
        dil="tr",
        baslik="Yeni model duyuruldu",
        ozet="Kısa özet",
        link="https://example.test/news/1",
        yayin_tarihi="2026-07-27T00:00:00+00:00",
    )

    with connect(db_path) as conn:
        init_db(conn)
        assert insert_news(conn, item) is True
        assert insert_news(conn, item) is False

        rows = list_news(conn)
        assert len(rows) == 1
        assert rows[0]["baslik"] == item.baslik
        assert "image_url" in rows[0]


def test_mark_discord_sent_removes_item_from_new_queue(tmp_path):
    db_path = tmp_path / "pulse.db"
    item = NewsItem(
        kaynak="Test Feed",
        kategori="community",
        dil="en",
        baslik="Open source AI tool",
        ozet=None,
        link="https://example.test/news/2",
    )

    with connect(db_path) as conn:
        init_db(conn)
        assert insert_news(conn, item) is True

        unsent = list_unsent_for_discord(conn)
        assert len(unsent) == 1
        assert mark_discord_sent(conn, unsent[0]["id"]) is True
        assert list_unsent_for_discord(conn) == []


def test_source_counts_group_by_source_category_and_language(tmp_path):
    db_path = tmp_path / "pulse.db"
    items = [
        NewsItem("A", "ai", "tr", "Bir", None, "https://example.test/a"),
        NewsItem("A", "ai", "tr", "İki", None, "https://example.test/b"),
        NewsItem("B", "research", "en", "Three", None, "https://example.test/c"),
    ]

    with connect(db_path) as conn:
        init_db(conn)
        for item in items:
            insert_news(conn, item)

        counts = source_counts(conn)
        assert counts[0]["kaynak"] == "A"
        assert counts[0]["haber_sayisi"] == 2
        assert counts[1]["kaynak"] == "B"
        assert counts[1]["haber_sayisi"] == 1
