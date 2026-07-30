from collector.collect import fetch_source, should_keep


class FakeResponse:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
      <channel>
        <title>Fake Feed</title>
        <item>
          <title>New GPT research lands</title>
          <link>https://example.test/gpt</link>
          <media:thumbnail url="https://example.test/gpt.jpg" />
          <description>Model news</description>
          <pubDate>Mon, 27 Jul 2026 00:00:00 GMT</pubDate>
        </item>
        <item>
          <title>Unrelated phone launch</title>
          <link>https://example.test/phone</link>
          <description>No AI signal here</description>
        </item>
      </channel>
    </rss>
    """

    def raise_for_status(self):
        return None


def test_fetch_source_filters_general_feeds_by_keywords(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("collector.collect.requests.get", fake_get)

    source = {
        "name": "Fake",
        "type": "rss",
        "url": "https://example.test/feed.xml",
        "lang": "en",
        "category": "genel",
    }

    name, items, error = fetch_source(source, ["gpt"], limit_per_source=10)

    assert name == "Fake"
    assert error is None
    assert len(items) == 1
    assert items[0].link == "https://example.test/gpt"
    assert items[0].image_url == "https://example.test/gpt.jpg"


def test_short_keywords_match_whole_words_only():
    source = {"category": "genel"}

    assert should_keep(source, "AI yeni nesil arama", None, ["ai"]) is True
    assert should_keep(source, "Bu cihaz aile moduna ait", None, ["ai"]) is False
