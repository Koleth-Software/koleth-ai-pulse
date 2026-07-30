from shared.config import load_sources_config, save_sources_config


def test_sources_config_can_use_database_backend(tmp_path, monkeypatch):
    db_path = tmp_path / "settings.db"
    source_file = tmp_path / "sources.yaml"
    source_file.write_text(
        """
sources:
  - name: Seed Feed
    type: rss
    url: https://example.test/feed.xml
    lang: tr
    category: ai
keywords_filter:
  - gpt
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("SOURCES_CONFIG_BACKEND", "database")

    seeded = load_sources_config(source_file)
    assert seeded["sources"][0]["name"] == "Seed Feed"

    seeded["sources"].append(
        {
            "name": "Second Feed",
            "type": "rss",
            "url": "https://example.test/second.xml",
            "lang": "en",
            "category": "research",
        }
    )
    save_sources_config(seeded, source_file)

    source_file.unlink()
    loaded = load_sources_config(source_file)
    assert [source["name"] for source in loaded["sources"]] == ["Seed Feed", "Second Feed"]
