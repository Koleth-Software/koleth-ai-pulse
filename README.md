# Koleth AI Pulse

Koleth AI Pulse, RSS/Atom kaynaklarından AI haberlerini toplayan, web panelinden yönetilebilen ve yeni haberleri Discord kanalına embed olarak gönderen açık kaynak haber hattıdır.

Proje iki şekilde çalışabilir:

- Yerel/self-hosted: SQLite ile tek makinede API, collector, web panel ve bot.
- Production/Vercel: Vercel üzerinde API + web panel + cron collector, ayrı bir sunucuda sürekli çalışan Discord botu, kalıcı veri için Postgres.

## Özellikler

- RSS/Atom kaynaklarından paralel haber toplama.
- Aynı haberin tekrar eklenmesini engelleyen benzersiz `link` alanı.
- Türkçe/İngilizce dil filtresi ve kategori filtresi.
- RSS görseli yakalama ve Discord embed içinde görsel gönderme.
- Web panelden kaynak, keyword filtresi ve Discord bot ayarlarını yönetme.
- SQLite ve Postgres desteği.
- Vercel Cron için `/api/cron/collect` endpointi.

## Hızlı Yerel Kurulum

```powershell
git clone https://github.com/koleth/koleth-ai-pulse.git
cd koleth-ai-pulse
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

API ve web panel:

```powershell
scripts\start-api.cmd
```

Web panel:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/yonetim
```

Discord bot:

```powershell
scripts\start-bot.cmd
```

## Ortam Değişkenleri

Temel değişkenler `.env.example` içinde bulunur.

```env
DB_PATH=data/koleth-ai-pulse.db
DATABASE_URL=
API_BASE_URL=http://127.0.0.1:8000
DISCORD_TOKEN=
DISCORD_CHANNEL_ID=
BOT_CONFIG_BACKEND=auto
SOURCES_CONFIG_BACKEND=auto
BOT_POLL_SECONDS=30
COLLECTOR_INTERVAL_SECONDS=3600
CRON_SECRET=
```

`DATABASE_URL` boşsa SQLite kullanılır. `DATABASE_URL` doluysa kaynaklar, bot ayarları ve haberler Postgres üzerinde tutulabilir.

## Web Panel

`/yonetim` panelinden şunlar yönetilir:

- RSS kaynakları
- Genel kaynaklar için AI keyword filtresi
- Discord bot aktif/pasif durumu
- Bot token ve kanal ID
- Discord'a gönderilecek haber dili
- Discord'a gönderilecek kategori
- Tur başına gönderilecek haber sayısı
- Sadece görselli haber gönderme filtresi
- Elle haber toplama

Token API yanıtında düz metin dönmez. Panel sadece token'ın kayıtlı olup olmadığını ve maskeli halini gösterir.

## Vercel + Ayrı Bot Sunucusu

Önerilen production mimarisi:

- Vercel: API, web panel, cron collector
- Postgres: haberler, gönderim kuyruğu, bot ayarları, kaynak ayarları
- VPS/Railway/Fly.io/systemd: Discord bot process'i

Vercel ortam değişkenleri:

```env
DATABASE_URL=postgresql://...
SOURCES_CONFIG_BACKEND=database
BOT_CONFIG_BACKEND=database
API_COLLECTOR_ENABLED=false
CRON_SECRET=uzun-rastgele-secret
ALLOWED_ORIGINS=https://senin-domainin.vercel.app
```

Vercel Cron `vercel.json` içinde saatlik ayarlı gelir:

```json
{
  "path": "/api/cron/collect",
  "schedule": "0 * * * *"
}
```

30 dakikada bir toplamak için:

```json
{
  "path": "/api/cron/collect",
  "schedule": "*/30 * * * *"
}
```

Bot sunucusundaki `.env`:

```env
DATABASE_URL=postgresql://...
BOT_CONFIG_BACKEND=database
API_BASE_URL=https://senin-domainin.vercel.app
```

Bot token ve kanal ID'yi web panelden kaydettiysen bot process'ini yeniden başlat.

## Docker

Docker kullanmak isteyenler için Compose dosyası vardır:

```powershell
docker compose up -d --build
```

Discord bot profili:

```powershell
docker compose --profile discord up -d --build
```

Docker bu proje için zorunlu değildir.

## API

- `GET /haberler?limit=&offset=&kaynak=&kategori=&dil=`
- `GET /haberler/yeni?limit=&dil=&kategori=&gorselli=`
- `POST /haberler/{id}/gonderildi`
- `GET /kaynaklar`
- `GET /health`
- `GET /yonetim/config`
- `GET /yonetim/bot`
- `PUT /yonetim/bot`
- `POST /yonetim/kaynaklar`
- `PUT /yonetim/kaynaklar/{name}`
- `DELETE /yonetim/kaynaklar/{name}`
- `PUT /yonetim/keywords`
- `POST /yonetim/topla`
- `GET /api/cron/collect`

## Güvenlik

- `.env`, `config/bot.yaml`, `data/`, `.venv/` ve `.tmp/` Git'e girmez.
- Discord token'ı açık kaynak repoya koymayın.
- Token sızarsa Discord Developer Portal üzerinden resetleyin.
- Yönetim panelini internete açıyorsanız reverse proxy, auth veya ağ kuralıyla koruyun.
- `CRON_SECRET` tanımlıysa cron endpointi `Authorization: Bearer <secret>` bekler.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Lisans

MIT
