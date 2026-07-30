# Koleth AI Pulse

Koleth AI Pulse, RSS/Atom kaynaklarından AI haberlerini toplayan, web panelinden yönetilebilen ve yeni haberleri Discord kanalına embed olarak gönderen açık kaynak haber hattıdır.

Proje iki şekilde çalışabilir:

- Yerel/self-hosted: SQLite ile tek makinede API, collector, web panel ve bot.
- Production/Vercel: Vercel üzerinde API + web panel, GitHub Actions ile collector tetikleme, ayrı bir sunucuda sürekli çalışan Discord botu, kalıcı veri için Postgres.

## Özellikler

- RSS/Atom kaynaklarından paralel haber toplama.
- Aynı haberin tekrar eklenmesini engelleyen benzersiz `link` alanı.
- Türkçe/İngilizce dil filtresi ve kategori filtresi.
- RSS görseli yakalama ve Discord embed içinde görsel gönderme.
- Web panelden kaynak, keyword filtresi ve Discord bot ayarlarını yönetme.
- SQLite ve Postgres desteği.
- Zamanlanmış toplama için `/api/cron/collect` endpointi.

## Hızlı Yerel Kurulum

```powershell
git clone https://github.com/koleth/koleth-ai-pulse.git
cd koleth-ai-pulse
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
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

- Vercel: API, web panel, collector endpointi
- GitHub Actions: saatlik collector tetikleme
- Postgres: haberler, gönderim kuyruğu, bot ayarları, kaynak ayarları
- VPS/Railway/Fly.io/systemd: Discord bot process'i

Vercel ortam değişkenleri:

```env
DATABASE_URL=postgresql://...
SOURCES_CONFIG_BACKEND=database
BOT_CONFIG_BACKEND=database
API_COLLECTOR_ENABLED=false
ADMIN_TOKEN=uzun-rastgele-admin-token
BOT_API_TOKEN=uzun-rastgele-bot-api-token
CRON_SECRET=uzun-rastgele-secret
ALLOWED_ORIGINS=https://senin-domainin.vercel.app
```

Vercel sadece `requirements.txt` içindeki API bağımlılıklarını kurar. Yerel geliştirme, test ve Discord bot için `requirements-dev.txt` kullanın.

Vercel Hobby hesaplarda cron job günde bir kezle sınırlıdır. Bu yüzden saatlik haber toplama `.github/workflows/collect-news.yml` içindeki GitHub Actions schedule ile yapılır:

```yaml
schedule:
  - cron: "0 * * * *"
```

GitHub repo ayarlarında şunları ekleyin:

```text
Settings -> Secrets and variables -> Actions

Secret:
CRON_SECRET=Vercel'deki CRON_SECRET ile aynı değer

Variable:
KOLETH_API_BASE_URL=https://senin-domainin.vercel.app
```

Bot sunucusundaki `.env`:

```env
DATABASE_URL=postgresql://...
BOT_CONFIG_BACKEND=database
API_BASE_URL=https://senin-domainin.vercel.app
API_AUTH_TOKEN=Vercel'deki BOT_API_TOKEN ile aynı değer
```

Web panelde yönetim işlemleri için `ADMIN_TOKEN` girilir. Bot token ve kanal ID'yi web panelden kaydettiysen bot process'ini yeniden başlat.

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

`/yonetim/*` endpointleri `ADMIN_TOKEN` ile korunur. `/haberler/yeni` ve `/haberler/{id}/gonderildi` endpointleri bot yayın kuyruğu için `BOT_API_TOKEN`, `API_AUTH_TOKEN` veya `ADMIN_TOKEN` kabul eder.

## Güvenlik

- `.env`, `config/bot.yaml`, `data/`, `.venv/` ve `.tmp/` Git'e girmez.
- Discord token'ı açık kaynak repoya koymayın.
- Token sızarsa Discord Developer Portal üzerinden resetleyin.
- Yönetim endpointleri `Authorization: Bearer <ADMIN_TOKEN>` ister. Production ortamında `ADMIN_TOKEN` tanımlı değilse yönetim kapalı kalır.
- Bot yayın kuyruğu endpointleri `Authorization: Bearer <BOT_API_TOKEN>` ister. Bot sunucusunda aynı değer `API_AUTH_TOKEN` olarak tanımlanır.
- `CRON_SECRET` tanımlıysa cron endpointi `Authorization: Bearer <secret>` bekler.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Lisans

MIT
