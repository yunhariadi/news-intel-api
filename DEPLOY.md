# DEPLOY.md — Running `news-intel-api` on a live VPS (real news)

This serves **real Indonesian news** (not the demo seed) from a single VPS using
the all-in-one mode: one API process fetches the real RSS feeds in
`apps/sources.py` on a schedule and serves the enriched results.

> Real-feed ingestion is on when `ENABLE_SCHEDULER=true`. The synthetic
> `DEV_SEED` is for local play only — keep it `false` in production.

---

## 0. What you need

- A VPS (Ubuntu 22.04/24.04, 1 vCPU / 1 GB RAM is enough to start).
- A domain name pointed at the VPS IP (for HTTPS).
- Outbound HTTPS from the VPS (to fetch the news feeds).

---

## 1. Provision the server

```bash
ssh root@YOUR_VPS_IP

# Docker + compose plugin
curl -fsSL https://get.docker.com | sh

# A non-root user (optional but recommended)
adduser app && usermod -aG docker app && su - app
```

## 2. Get the code

```bash
git clone <your-repo-url> news-intel-api   # or scp the directory up
cd news-intel-api
```

## 3. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set at least:

```ini
APP_ENV=production
REQUIRE_API_KEY=true                 # enforce keys in production
ENABLE_SCHEDULER=true                # fetch real feeds in-process
DEV_SEED=false
STORE_BACKEND=memory                 # no DB needed for the all-in-one
FETCH_INTERVAL_SECONDS=300           # how often to pull the feeds
# Use a REAL contact + bot-info URL (politeness / PR3):
USER_AGENT=NewsIntelBot/0.1 (+https://YOURDOMAIN/bot-info; contact: you@YOURDOMAIN)
API_KEY_SECRET=<run: openssl rand -hex 32>
```

## 4. Start it

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f api   # watch it fetch
```

You should see `ingest: new=… clusters=…` within a few seconds. It binds to
`127.0.0.1:8000` only — the reverse proxy below is the public entrypoint.

## 5. TLS reverse proxy (Caddy = automatic HTTPS)

```bash
sudo apt install -y caddy
echo 'YOURDOMAIN {
    reverse_proxy 127.0.0.1:8000
}' | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Caddy fetches a Let's Encrypt cert automatically. (nginx + certbot works too.)

## 6. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable          # 8000 stays internal — only Caddy reaches it
```

---

## 7. Set an API key and use it

With `REQUIRE_API_KEY=true`, all `/v1/*` routes (except `/v1/health`) need a key.
The access store is in-memory and **per-process**, so a key minted via
`docker compose exec` lives in a *different* process than the server and won't
work. Instead, seed a durable key at startup via `SEED_API_KEY` in `.env`:

```bash
# pick a key shaped like a real one (the nik_ prefix is required):
echo "SEED_API_KEY=nik_$(openssl rand -hex 32)" >> .env
docker compose -f docker-compose.prod.yml up -d   # recreate so it picks up .env
```

The server registers that exact value as a Business **admin** key on startup
(see `apps/api/main.py` lifespan). It survives restarts because it is re-seeded
from `.env` every boot. Use it directly as the bearer token:

```bash
KEY=nik_the_value_you_put_in_env
```

> Note: in-memory enrichment/trending/events still reset on restart and rebuild
> from the next feed window — only the **key** is now durable. For multi-process
> / horizontal scaling, move the access store to SQL (deferred — see DESIGN.md).


Then call it:

```bash
curl https://YOURDOMAIN/v1/health
curl -H "Authorization: Bearer $KEY" "https://YOURDOMAIN/v1/trending?type=topic&window=24h"
curl -H "Authorization: Bearer $KEY"  https://YOURDOMAIN/v1/events
curl -H "Authorization: Bearer $KEY"  https://YOURDOMAIN/v1/quotes
```

Public pages (no key): `/v1/health`, `/bot-info`, `/takedown`.

---

## 8. Operate

```bash
# update to latest code
git pull && docker compose -f docker-compose.prod.yml up -d --build

# logs / restart / stop
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml restart api
docker compose -f docker-compose.prod.yml down
```

`restart: unless-stopped` keeps it running across reboots/crashes.

---

## Without Docker (systemd)

```bash
sudo apt install -y python3-venv
python3 -m venv .venv && . .venv/bin/activate && pip install .
```

`/etc/systemd/system/news-intel.service`:

```ini
[Unit]
Description=news-intel-api
After=network-online.target

[Service]
WorkingDirectory=/home/app/news-intel-api
EnvironmentFile=/home/app/news-intel-api/.env
Environment=ENABLE_SCHEDULER=true
Environment=PYTHONPATH=/home/app/news-intel-api
ExecStart=/home/app/news-intel-api/.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
Restart=always
User=app

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now news-intel
```

---

## Important caveats (be honest about the scaffold)

- **State is in-memory and per-process.** The all-in-one works because the
  fetcher and the API are the *same* process. Do **not** run multiple replicas of
  this container behind a load balancer yet — each would have its own data.
  Horizontal scaling needs a shared (SQL) backend for enrichment/events/keys,
  which is deferred (DESIGN.md). One VPS = fine.
- **Restart clears enrichment/trending/events** (and in-memory keys); they
  rebuild from the next feed window within `FETCH_INTERVAL_SECONDS`. Set
  `STORE_BACKEND=sql` + the Postgres service from `docker-compose.yml` if you
  want raw articles to persist (enrichment of historical rows is not yet
  recomputed on boot).
- **Feed URLs are best-effort.** A 404/blocked feed is non-fatal (logged, the
  source is marked errored, the run continues). Check `/v1/sources/status` and
  edit `apps/sources.py` for your sources.
- **Compliance.** Real quotes are extracted only from real source text (never
  fabricated). Keep `/bot-info` + `/takedown` reachable and wire the DSR console
  (`POST /v1/admin/dsr`) to your takedown inbox.
