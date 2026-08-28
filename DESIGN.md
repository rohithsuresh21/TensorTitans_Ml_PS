# Design Notes & Roadmap

Working notes for the AI Security Pro system. These define where the product is going
and what to nail down before the demo/pitch.

## 1. Automatic Active Mode (Armed vs Idle)

The system should distinguish an **armed** state from an **idle** state instead of
running full detection 24/7.

- **Schedule-driven**: auto-activate outside business hours via a config-driven schedule
  (e.g., armed 18:00–08:00, weekdays only).
- **Manual toggle**: explicit arm/disarm (like a home security panel), so "restricted
  zone" violations during staffed hours don't create false positives.
- **Motion trigger**: run lightweight motion-diff on the raw stream; only fire full YOLO
  pose inference when something actually moves in frame — saving GPU/CPU cycles between
  events and reducing alert noise.

Benefits: fewer false-positive alerts when intrusions are expected, lower compute cost.

## 2. Deployment (Cost & VRAM)

Concrete numbers to nail down before demo:

- **Model footprint**: YOLO11m-pose @ 480px inference is roughly **2–4 GB VRAM** depending
  on batch/precision. YOLO11n/s-pose variants trade some accuracy for a fraction of the
  memory — relevant for Jetson/edge boxes vs cloud GPUs.
- **Cost story**:
  - On-device: Jetson Orin Nano (~$250 one-time)
  - Cloud GPU: recurring $/hr
  - Real customer question: *"what does this cost per camera per month?"*
- **Multi-camera scaling**: VRAM/cost multiply per stream unless frames from multiple
  cameras are batched into a single inference call.

## 3. Latency

End-to-end latency chain to measure and report:

`frame capture -> inference (480px YOLO pose) -> rule evaluation -> Telegram send
-> human confirm -> Twilio call placement`

- Frame-skip (every 2nd frame) trades latency for throughput — benchmark actual FPS and
  *detection-to-alert* time on target hardware. "How fast until police get called" is the
  number judges ask about for a security product.
- RTSP sources add their own latency (typically 200ms–2s depending on protocol/buffering)
  on top of inference time.

## 4. CCTV Working & APIs

- **CCTV integration**: most commercial systems expose RTSP
  (`rtsp://ip:port/stream`) or ONVIF. `cv2.VideoCapture` handles RTSP natively; ONVIF
  needs a small discovery library (`onvif-zeep`) to pull the stream URL first.
- **WhatsApp ruled out**: Meta Business API requires business verification, templated
  messages outside a 24h window, and per-message cost — not viable for a fast build.
- **Telegram Bot API is the right call**: free, instant setup via BotFather, inline
  buttons for the confirm flow, no approval process.
- **Twilio Voice** for the call leg: free trial tier is fine for the demo; production is
  per-minute cost.

## 5. Competitors & Differentiation

Commercial players in AI CCTV security: **Verkada, Rhombus, Ambient.ai, Deep Sentinel**.

Our baked-in differentiators:

- **Human-in-the-loop escalation** — most commercial systems are alert-only OR fully
  auto-escalate. Our Confirm/Dismiss flow is a genuine liability-conscious middle ground
  and a strong pitch point.
- **Customizable multi-zone rules from a click-to-define UI** — enterprise competitors
  typically need their own install/config team.
- **Multi-modal fusion** (pose + audio + fire/smoke) as a roadmap item — most competitors
  are vision-only.
- **Cost** — open-source models + Telegram + Twilio vs commercial per-camera SaaS fees.

## 6. Automatic Police Call (HIL)

Designed flow:

1. Detection fires
2. Telegram alert with inline **Confirm Emergency / False Alarm** buttons
3. `getUpdates` listener catches the callback
4. Only on **Confirm** does `Client.calls.create()` (Twilio) place the voice call
   reading out the alert type + zone

- Human-in-the-loop is the explicit safety design choice: this is **not** a fully
  autonomous police-dialer. That is both a legal risk (false alarms to real dispatch) and
  a trust concern for real deployments — state this clearly in the pitch.
- Optional backstop: timeout auto-escalation with a much higher confidence bar for cases
  where nobody is watching Telegram.

---

## Actions

- [x] Benchmark YOLO11m/n/s-pose VRAM + FPS on target hardware — 33.5 FPS @ 480px on RTX 4060 (GPU), ~5 FPS CPU
- [x] TensorRT export path (`export_tensorrt.py`) + GPU-first engine loading
- [x] Config schema for multi-zone rules + armed/idle schedule + tunables (conf/imgsz/frame-skip/faint/cooldown)
- [x] RTSP / local file / upload stream-source management + camera naming from the web UI
- [x] Carried-item detection (knife/scissors/suspicious) + intruder evidence capture to gallery
- [x] Telegram inline-button confirm/dismiss flow (voice call leg still open)
- [ ] Measure end-to-end detection-to-alert latency
- [ ] Motion-diff gate for full-inference on movement only
- [ ] Twilio voice call + timeout auto-escalation with high-confidence bar