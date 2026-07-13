#!/usr/bin/env python3
"""
Coco Cam — capture + detection service.
Reads the RTSP stream, classifies hamster activity by zone, logs events to Supabase.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("coco")

# ── Config (all tunable via env) ──────────────────────────────────────────────
RTSP_URL              = os.environ["RTSP_URL"]
SUPABASE_URL          = os.environ["SUPABASE_URL"]
SUPABASE_KEY          = os.environ["SUPABASE_SERVICE_KEY"]
WORKING_W             = int(os.environ.get("WORKING_WIDTH",            "640"))
WORKING_H             = int(os.environ.get("WORKING_HEIGHT",           "360"))
TARGET_FPS            = float(os.environ.get("TARGET_FPS",             "3"))
DEBOUNCE_SECS         = float(os.environ.get("DEBOUNCE_SECONDS",       "3"))
SLEEP_THRESHOLD_SECS  = float(os.environ.get("SLEEP_THRESHOLD_SECONDS","300"))
MOTION_THRESHOLD_PX   = int(os.environ.get("MOTION_THRESHOLD",         "500"))
CLIPS_DIR             = Path(os.environ.get("CLIPS_DIR",               "/clips"))
CLIPS_MAX             = int(os.environ.get("CLIPS_MAX",                "50"))
CLIP_PRE_SECS         = float(os.environ.get("CLIP_PRE_SECONDS",       "5"))
CLIP_POST_SECS        = float(os.environ.get("CLIP_POST_SECONDS",      "10"))
ZONE_CONFIG           = Path(os.environ.get("ZONE_CONFIG",             "/app/zone_config.json"))
SNAPSHOT_PATH         = Path(os.environ.get("SNAPSHOT_PATH",           "/snapshots/current.jpg"))
STATUS_PATH           = Path(os.environ.get("STATUS_PATH",             "/snapshots/status.json"))
ZONE_RELOAD_INTERVAL  = float(os.environ.get("ZONE_RELOAD_INTERVAL",   "60"))
# Webhook called on wake-up (HA REST API or any POST endpoint). Leave blank to disable.
WAKEUP_WEBHOOK_URL    = os.environ.get("WAKEUP_WEBHOOK_URL",           "")
NOTIFICATION_COOLDOWN = float(os.environ.get("NOTIFICATION_COOLDOWN",  str(SLEEP_THRESHOLD_SECS)))

FRAME_INTERVAL = 1.0 / TARGET_FPS

# ── Zone helpers ──────────────────────────────────────────────────────────────

def load_zones() -> dict:
    """Return {name: [[x,y], ...]} for zones that have polygons defined."""
    if not ZONE_CONFIG.exists():
        log.warning("zone_config.json not found — zone classification disabled")
        return {}
    with open(ZONE_CONFIG) as f:
        data = json.load(f)
    result = {}
    for z in data:
        if z.get("active", True) and len(z.get("polygon", [])) >= 3:
            result[z["name"]] = z["polygon"]
    return result


def point_in_zone(pt: tuple, polygon: list) -> bool:
    poly = np.array(polygon, dtype=np.int32)
    return cv2.pointPolygonTest(poly, (float(pt[0]), float(pt[1])), False) >= 0


def zone_for_centroid(centroid: Optional[tuple], zones: dict) -> Optional[str]:
    if centroid is None or not zones:
        return None
    for name, poly in zones.items():
        if point_in_zone(centroid, poly):
            return name
    return None

# ── State classification ──────────────────────────────────────────────────────

ACTIVE_STATES = {"exploring", "eating", "drinking", "active"}

def classify_raw(zone: Optional[str], is_moving: bool) -> str:
    if zone is None:
        return "hidden"      # not in any defined zone — buried or between zones
    if zone == "food":
        return "eating"
    if zone == "water":
        return "drinking"
    if zone == "explore" and is_moving:
        return "exploring"
    if not is_moving:
        return "still"       # in a zone, not moving → sleeping after threshold
    return "active"


def resolve_state(raw: str, duration_in_raw: float) -> str:
    """Promote 'still' → 'sleeping' once the threshold is met."""
    if raw == "still":
        return "sleeping" if duration_in_raw >= SLEEP_THRESHOLD_SECS else "active"
    return raw

# ── Clip writer ───────────────────────────────────────────────────────────────

class ClipWriter:
    def __init__(self, supabase):
        self._sb = supabase
        self._lock = threading.Lock()
        self._busy = False

    def trigger(self, frames: list, trigger_zone: Optional[str]):
        if self._busy:
            return
        threading.Thread(
            target=self._write, args=(list(frames), trigger_zone), daemon=True
        ).start()

    def _write(self, frames, trigger_zone):
        with self._lock:
            self._busy = True
            try:
                CLIPS_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                filename = f"coco_{ts}.mp4"
                filepath = CLIPS_DIR / filename
                if frames:
                    h, w = frames[0].shape[:2]
                    out = cv2.VideoWriter(
                        str(filepath),
                        cv2.VideoWriter_fourcc(*"mp4v"),
                        TARGET_FPS,
                        (w, h),
                    )
                    for f in frames:
                        out.write(f)
                    out.release()
                    duration = int(len(frames) / TARGET_FPS)
                    self._sb.table("clips").insert({
                        "filename": filename,
                        "trigger_zone": trigger_zone or "unknown",
                        "duration_seconds": duration,
                    }).execute()
                    log.info(f"Clip saved: {filename} ({duration}s, zone={trigger_zone})")
                    self._prune()
            except Exception as exc:
                log.error(f"Clip write error: {exc}")
            finally:
                self._busy = False

    def _prune(self):
        try:
            clips = (
                self._sb.table("clips")
                .select("id,filename,occurred_at")
                .order("occurred_at", desc=False)
                .execute()
                .data
            )
            for clip in clips[: max(0, len(clips) - CLIPS_MAX)]:
                (CLIPS_DIR / clip["filename"]).unlink(missing_ok=True)
                self._sb.table("clips").delete().eq("id", clip["id"]).execute()
        except Exception as exc:
            log.warning(f"Clip prune error: {exc}")

# ── Daily summary tracker ─────────────────────────────────────────────────────

_DURATION_COLS = {
    "sleeping":  "sleeping_seconds",
    "exploring": "exploring_seconds",
    "eating":    "eating_seconds",
    "drinking":  "drinking_seconds",
    "active":    "active_seconds",
    "hidden":    "hidden_seconds",
}
_VISIT_COLS = {
    "food": "food_visits",
    "water": "water_visits",
    "hide": "hide_visits",
    "explore": "explore_visits",
}


class SummaryTracker:
    def __init__(self, supabase):
        self._sb = supabase
        self._today = date.today()
        self._dur = {k: 0 for k in _DURATION_COLS}
        self._vis = {k: 0 for k in _VISIT_COLS}

    def _rollover(self):
        today = date.today()
        if today != self._today:
            self._flush()
            self._today = today
            self._dur = {k: 0 for k in _DURATION_COLS}
            self._vis = {k: 0 for k in _VISIT_COLS}

    def accumulate(self, state: str, zone: Optional[str], elapsed_secs: int, visit: bool = False):
        """Add elapsed time for state; optionally count a zone visit. Always flushes."""
        self._rollover()
        if state in _DURATION_COLS:
            self._dur[state] += elapsed_secs
        if visit and zone in _VISIT_COLS:
            self._vis[zone] = self._vis.get(zone, 0) + 1
        self._flush()

    def _flush(self):
        row = {
            "date": self._today.isoformat(),
            **self._dur,
            **{col: self._vis[zn] for zn, col in _VISIT_COLS.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._sb.table("daily_summaries").upsert(row, on_conflict="date").execute()
        except Exception as exc:
            log.error(f"Summary flush error: {exc}")

# ── Wake-up notification ──────────────────────────────────────────────────────

def send_wakeup_notification():
    if not WAKEUP_WEBHOOK_URL:
        return
    try:
        import urllib.request, urllib.error
        data = json.dumps({"event": "coco_active", "timestamp": datetime.now(timezone.utc).isoformat()})
        req = urllib.request.Request(
            WAKEUP_WEBHOOK_URL,
            data=data.encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        log.info("Wake-up webhook sent")
    except Exception as exc:
        log.warning(f"Wake-up webhook failed: {exc}")

# ── RTSP helpers ──────────────────────────────────────────────────────────────

def open_stream(url: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    supabase     = create_client(SUPABASE_URL, SUPABASE_KEY)
    clip_writer  = ClipWriter(supabase)
    summary      = SummaryTracker(supabase)

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    zones          = load_zones()
    zones_mtime    = ZONE_CONFIG.stat().st_mtime if ZONE_CONFIG.exists() else 0
    last_zone_chk  = time.monotonic()
    log.info(f"Zones loaded ({len(zones)} with polygons): {list(zones.keys())}")

    fgbg = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=16, detectShadows=False
    )

    pre_buf = deque(maxlen=int(CLIP_PRE_SECS * TARGET_FPS) + 1)

    # State machine
    current_state    = "active"
    raw_candidate    = "active"
    candidate_since  = time.monotonic()
    state_since      = time.monotonic()
    current_zone: Optional[str] = None

    # Periodic summary tick — accumulate current state every 60s without needing a transition
    TICK_INTERVAL = 60.0
    last_tick     = time.monotonic()

    # Clip post-recording
    clip_frames:       list          = []
    clip_post_remain:  float         = 0.0
    clip_trigger_zone: Optional[str] = None

    # Notification debounce
    last_notif = 0.0

    reconnect_delay = 5

    while True:
        cap = open_stream(RTSP_URL)
        if not cap.isOpened():
            log.warning(f"Stream unavailable, retry in {reconnect_delay}s")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)
            continue

        log.info("Stream open")
        reconnect_delay = 5
        read_errors     = 0
        last_frame_t    = 0.0

        while True:
            now = time.monotonic()

            # Throttle to TARGET_FPS
            if now - last_frame_t < FRAME_INTERVAL:
                time.sleep(max(0, FRAME_INTERVAL - (now - last_frame_t)))
                continue

            ret, raw = cap.read()
            if not ret:
                read_errors += 1
                log.warning(f"Frame read failure #{read_errors}")
                if read_errors > 10:
                    break
                time.sleep(0.5)
                continue

            read_errors  = 0
            last_frame_t = time.monotonic()

            frame = cv2.resize(raw, (WORKING_W, WORKING_H))

            # Reload zones if file changed or interval elapsed
            if time.monotonic() - last_zone_chk > ZONE_RELOAD_INTERVAL:
                last_zone_chk = time.monotonic()
                try:
                    mtime = ZONE_CONFIG.stat().st_mtime if ZONE_CONFIG.exists() else 0
                    if mtime != zones_mtime:
                        zones      = load_zones()
                        zones_mtime = mtime
                        log.info(f"Zones reloaded: {list(zones.keys())}")
                except Exception as exc:
                    log.warning(f"Zone reload error: {exc}")

            # Background subtraction
            fg = fgbg.apply(frame)
            fg = cv2.morphologyEx(
                fg, cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            )

            motion_px = int(fg.sum() / 255)
            is_moving = motion_px > MOTION_THRESHOLD_PX

            # Largest contour → centroid
            contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            centroid: Optional[tuple] = None
            if contours:
                lc = max(contours, key=cv2.contourArea)
                M  = cv2.moments(lc)
                if M["m00"] > 0:
                    centroid = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

            active_zone = zone_for_centroid(centroid, zones)
            raw_state   = classify_raw(active_zone, is_moving)

            # Debounce: candidate must persist for DEBOUNCE_SECS
            if raw_state != raw_candidate:
                raw_candidate   = raw_state
                candidate_since = time.monotonic()

            candidate_age  = time.monotonic() - candidate_since
            committed_raw  = raw_candidate if candidate_age >= DEBOUNCE_SECS else current_state

            state_age  = time.monotonic() - state_since
            new_state  = resolve_state(committed_raw, state_age)

            # Annotated snapshot for dashboard
            vis = frame.copy()
            for zname, poly in zones.items():
                pts = np.array(poly, dtype=np.int32)
                cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 100), thickness=1)
            if centroid:
                cv2.circle(vis, centroid, 6, (0, 0, 255), -1)
            cv2.putText(vis, f"{new_state} | {active_zone or '?'}", (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.imwrite(str(SNAPSHOT_PATH), vis)

            # Write status JSON
            status = {
                "current_state":         new_state,
                "zone":                  active_zone,
                "state_duration_seconds": int(state_age),
                "motion_px":             motion_px,
                "timestamp":             datetime.now(timezone.utc).isoformat(),
            }
            STATUS_PATH.write_text(json.dumps(status))

            # Periodic summary tick — flush current state time without waiting for a transition
            tick_now = time.monotonic()
            if tick_now - last_tick >= TICK_INTERVAL:
                elapsed = int(tick_now - last_tick)
                summary.accumulate(current_state, current_zone, elapsed)
                last_tick = tick_now

            # State transition handling
            if new_state != current_state:
                duration_secs = int(state_age)
                was_sleeping  = current_state == "sleeping"

                try:
                    supabase.table("events").insert({
                        "previous_state":  current_state,
                        "new_state":       new_state,
                        "zone":            active_zone or "unknown",
                        "duration_seconds": duration_secs,
                    }).execute()
                except Exception as exc:
                    log.error(f"Event insert error: {exc}")

                # Accumulate only time since the last tick (rest was already flushed)
                transition_now = time.monotonic()
                summary.accumulate(current_state, current_zone, int(transition_now - last_tick), visit=True)
                last_tick = transition_now

                # Wake-up: sleeping → active
                if was_sleeping and new_state in ACTIVE_STATES:
                    now_t = time.monotonic()
                    if now_t - last_notif >= NOTIFICATION_COOLDOWN:
                        last_notif = now_t
                        threading.Thread(target=send_wakeup_notification, daemon=True).start()
                    # Clip: pre-buffer + post
                    clip_frames       = list(pre_buf) + [frame.copy()]
                    clip_post_remain  = CLIP_POST_SECS
                    clip_trigger_zone = active_zone

                log.info(
                    f"[state] {current_state} → {new_state} "
                    f"(zone={active_zone}, dur={duration_secs}s)"
                )
                current_state = new_state
                current_zone  = active_zone
                state_since   = time.monotonic()

            # Continue recording post-trigger frames
            if clip_post_remain > 0:
                clip_frames.append(frame.copy())
                clip_post_remain -= FRAME_INTERVAL
                if clip_post_remain <= 0 and clip_frames:
                    clip_writer.trigger(clip_frames, clip_trigger_zone)
                    clip_frames = []

            pre_buf.append(frame.copy())

        cap.release()
        log.warning(f"Stream lost, reconnecting in {reconnect_delay}s")
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 60)


if __name__ == "__main__":
    main()
