# Katkı Rehberi

Katkılar memnuniyetle kabul edilir. Projenin hedefi küçük, anlaşılır ve kendi kendine kurulabilen bir AI haber hattı sağlamaktır.

## Kaynak Eklemek

Yeni RSS/Atom kaynakları için `config/sources.yaml` dosyasını düzenleyin veya çalışan kurulumda web panelini kullanın.

Gerekli alanlar:

- `name`: Kaynağın görünen adı
- `type`: Şimdilik `rss`
- `url`: RSS/Atom feed adresi
- `lang`: `tr`, `en` gibi dil kodu
- `category`: `ai`, `research`, `community` veya `genel`

`genel` kategorisindeki kaynaklar `keywords_filter` listesinden geçirilir. AI odaklı kaynaklarda `ai`, akademik feed'lerde `research`, topluluk kaynaklarında `community` kullanın.

## Kod Katkısı

1. Küçük ve odaklı pull request açın.
2. Bot ve web arayüzü doğrudan veritabanı okumamalı; API kontratını kullanmalı.
3. Tekrar engelleme davranışını koruyun: `link` benzersiz kalmalı.
4. Davranış değişiklikleri için test ekleyin.
5. Secret, token, lokal DB veya `.env` dosyası commit etmeyin.

## Yerel Kontrol

```bash
pip install -r requirements.txt
pytest
```

Scraping desteği ilk sürüm kapsamı değildir. RSS'i olmayan kaynaklar için önce issue açılması tercih edilir.
