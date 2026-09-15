# SentinelIQ

**Real-time CV security that watches restricted zones, detects intrusions, faints and carried items, and phones home over Telegram — live.**

SentinelIQ is a computer-vision security system that runs YOLOv11 pose detection live on any CCTV/RTSP feed. It flags restricted-zone intrusions, classifies faints and hands-up states, rescans intruder crops for carried items and weapons, and pushes annotated evidence to Telegram — all in real time, with a human-in-the-loop alert path.

Built by **TensorTitans ML** for hackathon and real-surveillance use alike.

---

## Why it stands out

| Concern | What SentinelIQ does |
| --- | --- |
| Zone breach | Pose-tracking engine flags any person entering a mapped restricted polygon and logs it as a zone breach |
| Faints & surrender | Pose keypoints distinguish medical distress (fall / faint) from compliant hands-up states |
| Carried items & weapons | On intrusion, intruder crops are rescanned with a carried-item detector to flag knives, bats and other objects |
| Alerting | Evidence + snapshot pushed to Telegram with a one-tap on-site alarm |
| Human-in-the-loop | Alerts are gated, reviewable and dismissible — no silent autonomous decisions |

---

## Live demo

> **No login required — open the demo and it just works.**

- **Live demo (feed + dashboard):** `https://frontend-theta-mocha-4dt0d7me5x.vercel.app`
- **API / backup shell:** `https://sentineliq-api-ndfx.onrender.com`

The demo runs a synthetic security feed at real inference speed. When the engine is offline, pages degrade gracefully to an offline placeholder instead of failing.

---

## Architecture

```
CCTV / RTSP / video file
        │
        ▼
┌─────────────────────────────┐
│  CV Engine (process-global   │
│  singleton: stream thread +  │
│  Telegram polling)           │
│  YOLOv11m-pose backbone      │
│  TensorRT when GPU present   │
└─────────────┬───────────────┘
              │ annotated frames / alerts
              ▼
┌─────────────────────────────┐          ┌──────────────────────────────┐
│  FastAPI backend (uvicorn,  │ ──────►  │  Telegram bot (evidence +    │
│  1 worker)                  │          │  snapshot, HIL approval)     │
│  SQLite (settings, zones,   │          └──────────────────────────────┘
│  users, evidence)           │
└─────────────┬───────────────┘
              │ JSON / MJPEG / JPEG
              ▼
┌──────────────────────────────────────┐
│  Frontend — dark operations-centre    │
│  Hero landing → Command Center      │
│  (dashboard, zones, settings, evidence)│
└──────────────────────────────────────┘
```

Key decisions:

- **Single-worker constraint** — the CV engine is a process-global singleton (stream + Telegram threads). The web server must run with one uvicorn worker; a reverse proxy fronts it for TLS.
- **Environment-driven config** — every knob (source, model, thresholds, parity, secrets) is a `.env` variable. Nothing is hardcoded.
- **Shell mode** — deploy a "control shell" without a camera/GPU (`RUN_ENGINE=0`): API, auth, zones, settings and evidence still work; live stream/snapshot return an offline placeholder.
- **Public demo mode** — `PUBLIC_MODE=1` removes the login wall for demo builds while keeping the owner cookie path intact.

---

## Tech stack

- **Inference:** Ultralytics YOLOv11m-pose, PyTorch, TensorRT (GPU), Supervision (tracking/annotations), OpenCV
- **Backend:** FastAPI, Uvicorn, SQLAlchemy, SQLite, Jinja2
- **Frontend:** Tailwind CSS (CDN), Chart.js, vanilla JS — dark security-console design (Orbitron / Manrope / JetBrains Mono)
- **Alerts:** python-telegram-bot HTTP API (requests), Telegram human-in-the-loop
- **Infra:** Docker, docker-compose (GPU + CPU), Render (shell API), Vercel + Cloudflare Tunnel (live frontend)

---

## Quick start (local)

```bash
# 1. clone and enter
git clone <repo-url>
cd <repo>

# 2. install
python -m venv venv
venv\Scripts\activate          # Windows
venv/bin/activate              # Linux / macOS
pip install -U pip
pip install -r requirements.txt

# 3. configure
cp .env.example .env           # edit: SECRET_KEY, TELEGRAM_*, source, model paths

# 4. run
python run.py                  # http://127.0.0.1:8000   (user: admin / see .env)
```

Or use the launchers: `scripts\start.ps1` (Windows) / `scripts/start.sh` (Linux).

### Point it at your own camera

Set in `.env`:

```dotenv
RTSP_STREAM_URL=rtsp://username:password@192.168.1.100:554/stream1
# or, for a local video file:
VIDEO_PATH=/abs/path/to/clip.mp4
```

The engine accepts either an RTSP URL (starts with `rtsp://`) or a video file path. Mixed sources and per-zone schedules are configurable from the Settings tab.

---

## Configuration reference

All config is environment-driven. Full list in `.env.example`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `RUN_ENGINE` | `1` = run CV engine + bot, `0` = API-only shell | `1` |
| `PUBLIC_MODE` | `1` = open pages/APIs without login (demo) | `0` |
| `APP_ENV` | `dev` / `prod` (gates cookie security, SECRET_KEY requirement) | `dev` |
| `SECRET_KEY` | Session-signing secret; **required** when `APP_ENV=prod` | auto-generated |
| `ALLOWED_HOSTS` | Comma-separated Host header allowlist | empty (any) |
| `RTSP_STREAM_URL` / `VIDEO_PATH` | Source selection (RTSP takes precedence when set) | — |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alert destination | empty |
| `MODEL_PATH` / `MODEL_ENGINE` | YOLO weights / TensorRT engine | `yolo11m-pose.pt` |
| `MODEL_CONF`, `MODEL_IMGSZ`, `FRAME_SKIP` | Detection tuning | `0.25` / `480` / `2` |
| `SEC_TO_FAINT`, `MSG_COOLDOWN` | Faint confirmation window, alert cooldown | `30` / `30` |
| `PORT` / `HOST` | Bind address | `0.0.0.0:8000` |
| `DATABASE_PATH` / `EVIDENCE_DIR` / `MEDIA_DIR` | Runtime data locations | repo defaults |

---

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe |
| GET | `/api/status` | Live status: fps, model, source, armed, running |
| GET | `/api/snapshot` | Current annotated frame (JPEG) |
| GET | `/api/stream` | MJPEG live stream |
| GET/POST | `/api/zones` , `/api/zone` | Restricted-zone maps |
| GET/POST | `/api/settings` | Detection tuning + schedule |
| POST | `/api/source` | Change camera/video source at runtime |
| POST | `/api/upload` | Upload a video clip to process |
| GET | `/api/evidence` | Alert evidence feed |
| POST | `/api/arm` / `/api/alarm` / `/api/dismiss` | Arm, trigger on-site alarm, dismiss alert |
| POST | `/api/viewer/heartbeat` | Viewer-activity signal for alert cooldown |

Interactive docs live at `/docs` (Swagger UI) when running locally.

---

## Deployment

See **[DEPLOY.md](DEPLOY.md)** for full detail. The short version:

- **Bare metal** — `python run.py` behind NGINX/Caddy; must stay a single uvicorn worker (see `scripts/systemd` example in DEPLOY.md).
- **Docker** — `docker compose up` (CPU) or `docker compose -f docker-compose.gpu.yml up` (GPU/TensorRT).
- **Shell API (Render)** — `render.yaml` deploys the API-only shell (`RUN_ENGINE=0`), always public via `PUBLIC_MODE=1`.
- **Live frontend** — static `frontend/` on Vercel, wired to the machine's localhost through a Cloudflare quick tunnel (`scripts/start-tunnel.ps1`).

---

## Repository layout

```
.
├── app/
│   ├── main.py            FastAPI app: pages, auth, API routes
│   ├── engine.py          CV engine: pipeline, pose, zones, alert gating
│   ├── database.py        SQLite (users, sessions, settings, zones, evidence)
│   ├── telegram_bot.py    Telegram HIL alert dispatcher
│   └── templates/         Backend-served pages (hero, dashboard, settings…)
├── frontend/              Vercel static frontend (hero, dashboard, picker)
├── public/                Specs and docs (hero-page-spec.md)
├── scripts/               run / start / tunnel / RTSP test-source helpers
├── media/                 Uploaded video sources
├── evidence/              Captured alert evidence
├── config.py              Environment-driven configuration
├── run.py                 Production entrypoint (single worker)
├── requirements.txt       Python dependencies
├── render.yaml            Render shell-API deployment
├── docker-compose.yml     CPU compose
└── docker-compose.gpu.yml GPU / TensorRT compose
```

---

## Safety & notes

- Change `DEFAULT_ADMIN_PASSWORD` before any public exposure.
- `PUBLIC_MODE=1` removes authentication entirely — intended for demo builds only.
- The engine requires a torch/GPU-capable runtime; the shell mode (`RUN_ENGINE=0`) runs on free cloud tiers.
- Evidence images and uploaded media are written under `evidence/` and `media/`.

---

## Team

**TensorTitans ML** — SentinelIQ
YOLOv11 · FastAPI · Telegram HIL