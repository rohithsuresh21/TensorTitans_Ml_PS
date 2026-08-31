# SentinelIQ - Deployment Guide

## Architecture notes (read first)

- The CV engine is a **process-global singleton** (camera/RTSP pipeline thread +
  Telegram polling). The web server **must run with a single uvicorn worker**.
  Do not scale workers or multiple replicas against the same stream.
- Persistence is a single SQLite file. Evidence images + uploaded videos are
  written to `EVIDENCE_DIR` / `MEDIA_DIR`.
- All configuration is environment driven (see `.env.example`).

## 1. Bare metal (Windows / Linux)

```bash
# once
python -m venv venv
venv\Scripts\activate        # Windows
venv/bin/activate            # Linux / macOS
pip install -U pip
pip install -r requirements.txt

cp .env.example .env         # then edit: SECRET_KEY, TELEGRAM_*, RTSP/VIDEO, model paths
python run.py                # https://127.0.0.1:8000   user: admin (see .env)
```

Or use the launchers:

- Windows: `powershell -ExecutionPolicy Bypass -File scripts\start.ps1`
- Linux:  `./scripts/start.sh`

### Production variables you must set

| Variable | Purpose |
| --- | --- |
| `APP_ENV=prod` | Enables prod defaults (secure cookie, requires SECRET_KEY) |
| `SECRET_KEY` | Fixed secret for session sanity (required when APP_ENV=prod) |
| `ALLOWED_HOSTS` | Comma-separated Host allowlist (yes, `localhost` + your FQDN) |
| `COOKIE_SECURE` | `1` when served over HTTPS |
| `TRUSTED_PROXY` | `1` when behind a reverse proxy (uses X-Forwarded-*) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alert chat |
| `DEFAULT_ADMIN_PASSWORD` | Change from the default before exposing publicly |
| `PORT` / `HOST` | Bind address (default `0.0.0.0:8000`) |
| `DATABASE_PATH`, `EVIDENCE_DIR`, `MEDIA_DIR` | Where runtime data lives |
| `MODELS_DIR` | Optional dir scanned for custom `*.pt` / `*.engine` models |

### Run as a service (systemd)

```ini
# /etc/systemd/system/sentineliq.service
[Unit]
Description=SentinelIQ
After=network.target

[Service]
WorkingDirectory=/opt/sentineliq
ExecStart=/opt/sentineliq/venv/bin/python run.py
Restart=always
User=sentineliq
EnvironmentFile=/opt/sentineliq/.env

[Install]
WantedBy=multi-user.target
```

## 2. Docker

CPU runtime (default):

```bash
mkdir -p models videos
cp export_tensorrt.py .          # optional
cp app/static/icon.svg .          # optional
cp .env.example .env              # configure it
docker compose up -d --build
```

NVIDIA GPU runtime (requires `nvidia-container-toolkit`), merge the override:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Mounts:

- `./models` (read-only) - your pose model(s); set `MODEL_PATH`/`MODEL_ENGINE`
- `./videos` (read-only) - local input clips for `VIDEO_PATH`
- `sentineliq-data` volume - SQLite DB, evidence, uploads

Add the TensorRT engine in the image or via `./models` and set `MODEL_ENGINE`.

## 3. Reverse proxy with TLS (recommended)

Single worker + `TRUSTED_PROXY=1`, then put Nginx/Caddy in front:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name sentineliq.example.com;

    location /api/stream {   # MJPEG: disable buffering
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1d;
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Also expose the `/health` endpoint to your monitoring stack.

## 3b. Public dashboard via Vercel + Cloudflare Tunnel (live engine stays local)

The web UI (auth, dashboard, settings, zone picker, evidence) is a static site
deployed on Vercel in `frontend/`. Its `/api/*` calls are rewritten to a backend
origin. There are **two** ways to wire that origin:

**Option A - Render shell (control plane, no live feed):**
- Deploy the repo on Render (`render.yaml`) with `RUN_ENGINE=0`. Auth, settings,
  zones and evidence work, but `/api/snapshot` and `/api/stream` return an offline
  placeholder frame (`app/static/offline-frame.jpg`).
- Point `frontend/vercel.json` `/api/:path*` at `https://<your-service>.onrender.com`.

**Option B - Cloudflare Tunnel (live feed, recommended):**
- Keep the full engine running on your own machine with `RUN_ENGINE=1` and expose
  port 8000 to the internet with a public (random) HTTPS URL:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\start-tunnel.ps1
  ```
  (First run downloads `cloudflared.exe`. Prints a `*.trycloudflare.com` URL and
  health-checks it for you. Save it in `trycloudflare-url.txt`.)
- The random URL changes on every restart: copy it into `frontend/vercel.json`
  (`/api/:path*` -> `destination`) and redeploy Vercel. For a permanent URL,
  create a named Cloudflare Tunnel bound to your own domain instead of the
  quick tunnel.
- Because traffic reaches the API over HTTPS through Cloudflare, also set
  `COOKIE_SECURE=1` in the local `.env` so sessions prefer the Secure cookie.

Deploy the static site once from `frontend/` on Vercel (root directory
`frontend`, Framework Preset "Other", output directory `.`). No build is needed.

## 4. Model placement

- Pose model: `yolo11m-pose.pt` (or a `.engine` TensorRT build for speed).
- If no model file is found the pipeline prints `[engine] no pose model found`.
- Generate a TensorRT engine with `python export_tensorrt.py` (CUDA GPU required).

## 5. Security checklist

- [ ] `SECRET_KEY` set, `APP_ENV=prod`, `ALLOWED_HOSTS` configured
- [ ] `DEFAULT_ADMIN_PASSWORD` changed (or seed your own user via DB)
- [ ] HTTPS terminated at the reverse proxy; `COOKIE_SECURE=1`
- [ ] Telegram credentials live only in `.env` (gitignored)
- [ ] Evidence/media directories excluded from source control (already gitignored)
- [ ] Single worker/replica - never parallel instances on one stream