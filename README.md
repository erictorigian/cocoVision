# Coco Cam

Kid-friendly hamster activity dashboard. Monitors Coco via RTSP camera, classifies
activity by zone (sleeping / exploring / eating / drinking), logs to Supabase, and
displays everything on a playful dashboard at `coco.torigian.com`.

---

## Quick Start

```bash
# 1. Create your .env from the template
cp .env.example .env
# Edit .env — fill in SUPABASE_SERVICE_KEY at minimum

# 2. Build and start
docker compose up -d --build

# 3. Run zone calibration (first time, or after rearranging the cage)
docker compose --profile calibrate up calibrator
# Visit http://10.27.27.6:7070 — draw your zones — click Save — stop the container

# 4. Restart detector to pick up new zones
docker compose restart detector
```

---

## Zone Calibration

> **If Coco's activity tracking looks wrong, re-calibration is the first thing to try.**
> This happens naturally if you rearrange cage furniture or if the camera shifts.

1. `docker compose --profile calibrate up calibrator`
2. Open **http://10.27.27.6:7070** in a browser
3. Select a zone (Hide Box, Food Bowl, Water Bottle, Open/Tunnels)
4. Click to place polygon points around that region in the camera frame
5. Double-click (or click near the first point) to close each polygon
6. Click **Save Zones** when all zones are drawn
7. `docker compose --profile calibrate down calibrator`
8. `docker compose restart detector` — new zones load within 60 seconds

The wheel zone is reserved for future use. Leave it empty until the wheel is installed.

---

## Reverse Proxy Setup

Point `coco.torigian.com` to the `dashboard` container (port 80).
The dashboard's nginx already proxies `/api/*` internally to the `api` container —
you only need one subdomain.

**nginx example:**
```nginx
server {
    server_name coco.torigian.com;
    location / {
        proxy_pass http://10.27.27.6:3000;  # dashboard container port
        proxy_set_header Host $host;
    }
}
```

If your homelab uses a different port mapping, adjust accordingly.
The `api` container does NOT need its own subdomain.

---

## Detection Tuning

All thresholds are env vars in `.env` — adjust and `docker compose restart detector`:

| Variable | Default | Effect |
|---|---|---|
| `TARGET_FPS` | `3` | Frames processed per second |
| `MOTION_THRESHOLD` | `500` | Pixel count to consider "moving" — raise if noisy |
| `DEBOUNCE_SECONDS` | `3` | Seconds before a state change is committed |
| `SLEEP_THRESHOLD_SECONDS` | `300` | Seconds of stillness before "sleeping" is declared |
| `CLIP_PRE_SECONDS` | `5` | Pre-event buffer saved with each clip |
| `CLIP_POST_SECONDS` | `10` | Post-event recording after wake-up |

If you see rapid state flicker: raise `DEBOUNCE_SECONDS` or `MOTION_THRESHOLD`.
If sleeping is declared too quickly: raise `SLEEP_THRESHOLD_SECONDS`.

---

## Alexa / Home Assistant Wake-Up Notification

When HA is ready:

1. Set `WAKEUP_WEBHOOK_URL` in `.env` to your HA webhook or REST API endpoint.
2. The detector POSTs `{"event":"coco_active","timestamp":"..."}` there when Coco
   wakes up after a sleep period.
3. Create an HA automation that triggers an Alexa TTS announcement on that call.
4. `NOTIFICATION_COOLDOWN` (seconds) controls how long before re-notifying.

The notification path is completely decoupled from the tracking pipeline — breaking it
won't affect detection or logging.

---

## Viewing Logs

```bash
docker compose logs -f detector   # detection + state transitions
docker compose logs -f api        # API requests
docker compose logs -f dashboard  # nginx access log
```

---

## File Structure

```
cocoCam/
├── detector/           Python capture + detection service
│   ├── main.py
│   └── zone_config.json   bind-mounted; written by calibrator
├── calibrator/         One-shot web tool for drawing zones
├── api/                FastAPI layer (Supabase + file serving)
├── dashboard/          React + Vite, served by nginx
├── docker-compose.yml
├── .env                (create from .env.example, never commit)
└── .env.example
```

Highlight clips are stored in the `coco-clips` Docker volume.
To inspect: `docker run --rm -v cocoCam_coco-clips:/clips alpine ls /clips`
