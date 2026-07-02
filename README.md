# pricewatch-bot

Telegram bot that sends **Amazon India price-drop alerts**. Users track
products via the bot; a scheduled poller snapshots prices and alerts when a
product falls at or below a chosen % under its **90-day median** price.

## Price sources

Set `PRICE_SOURCE` in `.env`:

- **`scraper` (default)** — fetches amazon.in product pages directly and
  parses the price/title/category. No affiliate account or credentials
  needed; alert links are plain product URLs. Trade-offs: page markup can
  change without notice, and Amazon may serve CAPTCHA/503 responses if
  polled too aggressively (the poller paces requests ~2.5–4 s apart and
  skips blocked products for the run).
- **`creators`** — Amazon Creators API (requires `CREATORS_CLIENT_ID`,
  `CREATORS_CLIENT_SECRET`, `PARTNER_TAG`); alert links carry your
  affiliate tag.

## ⚠️ Important caveats

- **Alert warm-up:** there is no external price-history source — the poller
  accumulates its own snapshots. A product needs **at least 10 snapshots
  (~10 days at one poll/day)** before any alert can fire.
- **Creators API eligibility** (only if `PRICE_SOURCE=creators`): Amazon
  requires **10 qualifying sales in a trailing 30-day window** to keep API
  access active, and the request/response shapes in
  `pricewatch/sources/creators.py` are marked `# confirm against docs` —
  verify them against Associates Central documentation before use.

## How it works

- `pricewatch/bot.py` — long-running Telegram bot (`/start`, `/track <url|ASIN> [drop%]`,
  `/categories a, b`, `/list`). Thresholds default to 50%, clamped 1–95.
- `pricewatch/poller.py` — periodic job: one fetch per tracked ASIN
  (~1.1 s apart to respect the Creators API 1 TPS / 8640-per-day starter
  limit), snapshot the price, then evaluate every tracking of that product.
- `pricewatch/compare.py` — pure logic: median-of-90-days baseline,
  ≥10-snapshot gate, threshold check, and de-dupe (re-alert only on a
  strictly lower price).
- `pricewatch/sources/` — `PriceSource` abstraction; `ScraperSource`
  (default) and `CreatorsAPISource` implemented; new sources drop in
  without touching anything else.
- `pricewatch/notify/` — `Notifier` abstraction; `TelegramNotifier`
  implemented, `whatsapp.py` holds a stub noting the WhatsApp Cloud API
  24-hour-window / template-message rule.
- `pricewatch/db.py` — all SQL (psycopg v3); schema in `schema.sql`.

## Setup

```bash
# 1. Postgres
createdb pricewatch
psql pricewatch < schema.sql

# 2. Python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Config
cp .env.example .env   # fill in tokens/credentials
```

## Run locally

```bash
set -a; source .env; set +a
python -m pricewatch.bot      # the Telegram bot (long-running)
python -m pricewatch.poller   # one poll pass (schedule this)
```

Tests:

```bash
pytest tests/
```

## Deploy on a DigitalOcean droplet (systemd)

Assumes the repo lives at `/opt/pricewatch-bot` with a venv at
`/opt/pricewatch-bot/.venv` and env vars in `/opt/pricewatch-bot/.env`.

`/etc/systemd/system/pricewatch-bot.service` (long-running bot):

```ini
[Unit]
Description=pricewatch Telegram bot
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
WorkingDirectory=/opt/pricewatch-bot
EnvironmentFile=/opt/pricewatch-bot/.env
ExecStart=/opt/pricewatch-bot/.venv/bin/python -m pricewatch.bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/pricewatch-poller.service` (oneshot poll pass):

```ini
[Unit]
Description=pricewatch price poller (one pass)
After=network-online.target postgresql.service

[Service]
Type=oneshot
WorkingDirectory=/opt/pricewatch-bot
EnvironmentFile=/opt/pricewatch-bot/.env
ExecStart=/opt/pricewatch-bot/.venv/bin/python -m pricewatch.poller
```

`/etc/systemd/system/pricewatch-poller.timer`:

```ini
[Unit]
Description=Run pricewatch poller every 6 hours

[Timer]
OnCalendar=*-*-* 00/6:00:00
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
```

Enable everything:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pricewatch-bot.service
sudo systemctl enable --now pricewatch-poller.timer
```

## Extending

- **New price source:** subclass `pricewatch.sources.base.PriceSource`
  (e.g. a scraper) and swap it into `poller.py` — nothing else changes.
- **New alert channel:** implement `pricewatch.notify.base.Notifier`
  (see the WhatsApp stub for constraints).
