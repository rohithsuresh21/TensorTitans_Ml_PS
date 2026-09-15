# SentinelIQ — Hero Page Spec

This document is the **single source of truth for the hero (landing) page only**.
It defines the exact copy, colors, fonts, assets, section list, and layout rules.
Any page after the hero (Projects, About, Contact, etc.) is **your own prompt** —
do not guess its look from here.

---

## 1. Page identity & positioning

- Product name: **SentinelIQ** (spelled exactly — no spaces, no hyphen).
- Maker tag: **TensorTitans ML** (team/studio credit).
- One-line positioning:
  > **Real-time CV security that watches restricted zones, detects intrusions,
  > faints and carried items, and phones home over Telegram — live.**
- Tone: technical, calm, confident, slightly ominous but not gimmicky.
  Think security-operations centre, not a consumer gadget.
- Audience: judges (hackathon), technical evaluators, and a CCTV/RTSP integrator.

---

## 2. Exact copy (headline, sub, buttons, sections)

### Hero (top fold)
- **Headline:** `SENTINELIQ` (logo-style wordmark, see §4 asset)
- **Eyebrow / kicker (mono, small):** `YOLO11 POSE · RTSP · TELEGRAM HIL`
- **Sub-headline (display):**
  `One camera stream. Every intrusion, faint, and carried weapon — caught in real time.`
- **Supporting line (sans, muted):**
  `SentinelIQ runs YOLOv11 pose detection live on any CCTV/RTSP feed, classifies
  restricted-zone intrusions, scans intruders for carried items and weapons, and
  pushes instant alerts to your Telegram.`
- **Primary CTA button:** `OPEN COMMAND CENTER` → links to the live dashboard.
- **Secondary CTA link:** `VIEW THE PIPELINE` → scrolls to §4 section below.

### Feature section — "Detects" (3 core capabilities)
1. **Intrusion detection**
   - `Restricted-zone breaches` — a pose-tracking engine flags any person entering
     a mapped restricted polygon and logs it as a zone breach.
2. **Medical / compliance events**
   - `Faints & hands-up` — pose keypoints classify falls (faint) and compliant
     hands-up states, separating medical distress from surrender.
3. **Carried-item & weapon scan**
   - `Weapon / edge scan` — on intrusion, intruder crops are rescanned with a
     carried-item detector to flag knives, bats and other carried objects.

### "How it works" section — 4 steps (short, sequential)
1. `STREAM` — Connect any RTSP / CCTV / video source.
2. `INFER` — YOLOv11 pose runs live, TensorRT-accelerated when a GPU is present.
3. `DECIDE` — Restricted-zone + faint/arms classification gates every alert.
4. `ALERT` — Evidence + snapshot pushed to Telegram with a one-tap on-site alarm.

### Stats bar (one line of 3–4 strong numbers from the live engine)
- `fps` — current GPU inference throughput (e.g. `51 fps`).
- `model` — `yolo11m-pose` (pose backbone).
- `latency` — alert pipeline from breach to Telegram push.

> Values shown are whatever the running engine reports; the bar is live, not static.

### About / closing block (1 short paragraph)
> Built for hackathons and real surveillance alike, SentinelIQ pairs a PyTorch
> pose model with a process-singleton CV engine, a hardened FastAPI backend, and
> a Telegram human-in-the-loop alert path — so a single camera can watch a room,
> a depot, or a restricted area and tell you the moment something is wrong.

### Footer line
- Left: `TENSORTITANS ML · SENTINELIQ`
- Right: `YOLO11 · FASTAPI · TELEGRAM HIL`

---

## 3. Colors, fonts, tokens — must mirror the dashboard ("same as hero" applies)

Reuse the exact palette and typography already in the app UI (`dashboard.html`,
`login.html`, `app/static/style.css`). Do NOT invent new colors or fonts.

### Colors
- **Page background:** near-black `#05070d`
- **Surface (cards):** `bg-white/[0.03]` on the dark bg, `1px` border `white/10`
- **Primary accent:** emerald `#10b981` → text/`#34d399` hover (specifically the
  emerald family already used: `emerald-400`/`emerald-500`/`emerald-600`)
- **Danger accent:** red for alerts / weapons (`red-400`–`red-500`)
- **Warning accent:** amber for compliance/amber status (`amber-400`–`amber-500`)
- **Body text muted:** slate `#94a3b8` (`slate-400`), faint `slate-600`
- **Headers:** white (`text-white`) where strong, `slate-400` when muted
- **Logo glow:** drop shadow `0 0 12px rgba(52,211,153,0.5)` (emerald)

### Fonts (Google Fonts, already loaded)
- **Display / headlines:** Orbitron (weights 600/700/900) — use `font-display`,
  uppercase with `tracking-[0.25em]`-style wide letter-spacing for the wordmark.
- **Body / UI:** Manrope (400/600/700/800) — `font-sans`.
- **Mono / labels / eyebrows / stats:** JetBrains Mono (400/500/700) — `font-mono`,
  uppercase, `tracking-widest` for eyebrows and button labels.

### Tokens
- Radius: `rounded-xl` / `rounded-2xl` (cards), `rounded-lg` (buttons/chips).
- Border: `border-white/10` on surfaces.
- Buttons: primary = `bg-emerald-600` → `hover:bg-emerald-500`, white text,
  `text-xs font-semibold` uppercase; secondary = `bg-white/5` + `border-white/10`
  + `hover:bg-white/10`.
- The whole page keeps the same **dark operations-centre** feel: no gradients
  toward pink/blue, no glassmorphism light-mode, no generic SaaS look.

---

## 4. Asset URLs

- **Logo / icon:** `app/static/icon.svg` — the SentinelIQ logo (user's own SVG,
  185,458 bytes, served as `image/svg+xml`). Use this as the favicon, nav mark,
  and hero wordmark echo (size ~`w-9 h-9` to `w-16 h-16`).
- **Fonts:**
  `https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Manrope:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap`
- **Tailwind (CDN):** `https://cdn.tailwindcss.com` (matching how the existing
  pages load it); configure `font-family` display/sans/mono the same way:
  `display:['Orbitron','sans-serif']`, `sans:['Manrope','sans-serif']`,
  `mono:['JetBrains Mono','monospace']`.
- **Charts (if any hero visual needs one):** Chart.js
  `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js`
- **No photos/stock imagery.** Any visual should be live product output
  (the CV-annotated snapshot) or the logo. If a camera frame is shown, pull it
  from the backend `/api/snapshot`; otherwise use the offline placeholder
  `app/static/offline-frame.jpg`. **Do not use generic security-stock photos.**

---

## 5. Section list for the hero page (in order)

1. **Nav bar** — SentinelIQ logo + wordmark, links to the other pages
   (Command Center / dashboard, plus any page names from your own prompt),
   and the primary CTA button.
2. **Hero** — eyebrow, headline, sub, supporting line, primary + secondary CTAs,
   featured live snapshot/frame.
3. **Stats bar** — live fps / model / latency from the engine (see §2).
4. **Detects** — 3 capability cards (intrusion, faints/hands-up, carried items).
5. **How it works** — 4 numbered steps (Stream → Infer → Decide → Alert).
6. **About / closing** — product mission paragraph + logo signature.
7. **Footer** — TensorTitans ML · SentinelIQ credit line.

---

## 6. Layout & animation rules (hero page)

- Dark near-black background, light content — same as the dashboard.
- Section max-width ~`max-w-[1600px]`, padded `p-4 md:p-6`, page content wrapped
  in a `.max-w-*` container per section.
- **Typography hierarchy:** `font-display` for big headers, `font-sans` for body,
  `font-mono` (uppercase) for eyebrows, labels, buttons, and stats.
- Subtle, not flashy: rely on Tailwind `transition` (e.g. `hover:bg-white/10`,
  `transition-all duration-700` on value bars), a faint `backdrop-blur` on the
  sticky nav (`bg-[#05070d]/70`), and a `drop-shadow` on the logo.
- Cards: `bg-white/[0.03]` + `border-white/10` + `rounded-2xl` — flat, dark,
  no heavy shadows, no bold 3D.
- Any live value (fps, model, event feed) updates in place with a smooth
  CSS transition — same as the dashboard KPI bars.
- **No AI look:** no gradient mesh backgrounds, no purple/pink accents, no
  floating 3D blobs, no emoji, no over-animated reveals. Keep it precise,
  monospace-labelled, and dark like a real security console.

---

## 7. How to reuse backend endpoints (if the hero shows live data)

- Health: `GET /api/health` → `{"status":"ok",...}`
- Live status + fps/model/armed: `GET /api/status` (requires session cookie;
  the hero may show a public/static snapshot instead if not logged in)
- Live annotated frame: `GET /api/snapshot` (auth) or static
  `app/static/offline-frame.jpg` when unauthenticated/offline.

> Keep the hero **public** (no login wall). If you show live numbers, degrade
> gracefully to static values/placeholders when the engine is offline.
