from fastapi.testclient import TestClient
import yaml

from api.main import app
from shared.db import NewsItem, connect, init_db, insert_news


def test_api_lists_news_and_marks_discord_sent(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    with connect(db_path) as conn:
        init_db(conn)
        insert_news(
            conn,
            NewsItem(
                kaynak="API Feed",
                kategori="ai",
                dil="tr",
                baslik="API haberi",
                ozet="Özet",
                link="https://example.test/api",
            ),
        )

    with TestClient(app) as client:
        response = client.get("/haberler", params={"kategori": "ai"})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["kaynak"] == "API Feed"

        new_response = client.get("/haberler/yeni")
        assert new_response.status_code == 200
        new_rows = new_response.json()
        assert len(new_rows) == 1

        mark_response = client.post(f"/haberler/{new_rows[0]['id']}/gonderildi")
        assert mark_response.status_code == 200

        assert client.get("/haberler/yeni").json() == []


def test_api_filters_new_discord_queue(tmp_path, monkeypatch):
    db_path = tmp_path / "filtered-new.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    with connect(db_path) as conn:
        init_db(conn)
        insert_news(conn, NewsItem("TR Feed", "ai", "tr", "TR haber", None, "https://example.test/tr", image_url="https://example.test/tr.jpg"))
        insert_news(conn, NewsItem("EN Feed", "ai", "en", "EN news", None, "https://example.test/en"))
        insert_news(conn, NewsItem("TR Feed", "genel", "tr", "Genel", None, "https://example.test/genel"))

    with TestClient(app) as client:
        response = client.get("/haberler/yeni", params={"dil": "tr", "kategori": "ai", "gorselli": True})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["baslik"] == "TR haber"


def test_api_source_counts(tmp_path, monkeypatch):
    db_path = tmp_path / "sources.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    with connect(db_path) as conn:
        init_db(conn)
        insert_news(conn, NewsItem("Count Feed", "research", "en", "One", None, "https://example.test/one"))

    with TestClient(app) as client:
        response = client.get("/kaynaklar")
        assert response.status_code == 200
        assert response.json()[0]["haber_sayisi"] == 1


def test_api_serves_website_index(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "website.db"))

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Koleth AI Pulse" in response.text

        asset_response = client.get("/assets/pulse-grid.svg")
        assert asset_response.status_code == 200
        assert "image/svg+xml" in asset_response.headers["content-type"]


def test_admin_source_config_endpoints(tmp_path, monkeypatch):
    db_path = tmp_path / "admin.db"
    config_path = tmp_path / "sources.yaml"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("SOURCES_CONFIG", str(config_path))
    config_path.write_text("sources: []\nkeywords_filter:\n  - yapay zeka\n", encoding="utf-8")

    with TestClient(app) as client:
        add_response = client.post(
            "/yonetim/kaynaklar",
            json={
                "name": "Yeni Türkçe Kaynak",
                "type": "rss",
                "url": "https://example.test/feed.xml",
                "lang": "tr",
                "category": "genel",
            },
        )
        assert add_response.status_code == 200
        assert add_response.json()["sources"][0]["name"] == "Yeni Türkçe Kaynak"

        keyword_response = client.put(
            "/yonetim/keywords",
            json={"keywords_filter": ["gpt", "gpt", "yapay zeka", ""]},
        )
        assert keyword_response.status_code == 200
        assert keyword_response.json()["keywords_filter"] == ["gpt", "yapay zeka"]

        delete_response = client.delete("/yonetim/kaynaklar/Yeni%20T%C3%BCrk%C3%A7e%20Kaynak")
        assert delete_response.status_code == 200
        assert delete_response.json()["sources"] == []

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["keywords_filter"] == ["gpt", "yapay zeka"]


def test_admin_bot_settings_endpoint_masks_token(tmp_path, monkeypatch):
    config_path = tmp_path / "bot.yaml"
    monkeypatch.setenv("BOT_CONFIG", str(config_path))
    monkeypatch.setenv("DISCORD_TOKEN", "")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "")

    with TestClient(app) as client:
        response = client.put(
            "/yonetim/bot",
            json={
                "enabled": True,
                "discord_token": "abc123456789xyz",
                "channel_id": "1530629908789854229",
                "publish_language": "tr",
                "publish_category": "ai",
                "poll_seconds": 30,
                "max_per_cycle": 3,
                "require_image": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["token_set"] is True
        assert "discord_token" not in payload
        assert payload["channel_id"] == "1530629908789854229"
        assert payload["publish_language"] == "tr"
        assert payload["require_image"] is True

        get_response = client.get("/yonetim/bot")
        assert get_response.status_code == 200
        assert get_response.json()["token_mask"] == "abc123...9xyz"


def test_bot_settings_can_use_database_backend(tmp_path, monkeypatch):
    db_path = tmp_path / "settings.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_CONFIG_BACKEND", "database")
    monkeypatch.setenv("DISCORD_TOKEN", "")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "")

    with TestClient(app) as client:
        response = client.put(
            "/yonetim/bot",
            json={
                "enabled": False,
                "discord_token": "database-token-123",
                "channel_id": "123456789",
                "publish_language": "en",
                "publish_category": "",
                "poll_seconds": 45,
                "max_per_cycle": 2,
                "require_image": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        get_response = client.get("/yonetim/bot")
        assert get_response.status_code == 200
        payload = get_response.json()
        assert payload["channel_id"] == "123456789"
        assert payload["publish_language"] == "en"
        assert payload["token_set"] is True
