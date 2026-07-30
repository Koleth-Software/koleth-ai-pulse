from bot.bot import format_datetime_label, language_flag, make_embed


def test_language_flag_maps_known_languages():
    assert language_flag("tr") == "🇹🇷"
    assert language_flag("en") == "🇬🇧"
    assert language_flag("de") == "DE"


def test_format_datetime_label_uses_turkish_display():
    assert format_datetime_label("2026-07-29T14:39:00+00:00") == "29 Temmuz 2026 17:39"


def test_embed_uses_flag_and_formatted_date():
    embed = make_embed(
        {
            "baslik": "Test",
            "link": "https://example.test/news",
            "ozet": "Özet",
            "kaynak": "Kaynak",
            "kategori": "ai",
            "dil": "tr",
            "yayin_tarihi": "2026-07-29T14:39:00+00:00",
        }
    )

    fields = {field.name: field.value for field in embed.fields}
    assert fields["Dil"] == "🇹🇷"
    assert fields["Yayın"] == "29 Temmuz 2026 17:39"
