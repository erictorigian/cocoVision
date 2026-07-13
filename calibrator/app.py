"""
Coco Cam — zone calibrator.
Run with --profile calibrate, visit http://localhost:7070, draw zones, save.
Writes to zone_config.json and updates Supabase zones table.
"""

import json
import os
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_file, send_from_directory
from supabase import create_client

RTSP_URL     = os.environ["RTSP_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
WORKING_W    = int(os.environ.get("WORKING_WIDTH",  "640"))
WORKING_H    = int(os.environ.get("WORKING_HEIGHT", "360"))
ZONE_CONFIG  = Path(os.environ.get("ZONE_CONFIG",   "/app/zone_config.json"))

app     = Flask(__name__, static_folder="static")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

_frame_cache: bytes | None = None
_frame_ts:    float        = 0.0
CACHE_TTL = 5.0  # seconds


def grab_frame() -> bytes | None:
    global _frame_cache, _frame_ts
    now = time.monotonic()
    if _frame_cache and now - _frame_ts < CACHE_TTL:
        return _frame_cache

    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    ok, frame = False, None
    for _ in range(10):   # skip buffered frames to get a recent one
        ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None

    frame = cv2.resize(frame, (WORKING_W, WORKING_H))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    _frame_cache = buf.tobytes()
    _frame_ts    = now
    return _frame_cache


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/frame")
def frame():
    data = grab_frame()
    if data is None:
        return "Could not capture frame from stream", 503
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(data)
    tmp.close()
    return send_file(tmp.name, mimetype="image/jpeg")


@app.route("/zones", methods=["GET"])
def get_zones():
    if ZONE_CONFIG.exists():
        with open(ZONE_CONFIG) as f:
            return jsonify(json.load(f))
    return jsonify([])


@app.route("/zones", methods=["POST"])
def save_zones():
    zones = request.get_json()
    if not isinstance(zones, list):
        return jsonify({"error": "expected list"}), 400

    # Write config file
    ZONE_CONFIG.write_text(json.dumps(zones, indent=2))

    # Update Supabase zones table
    for z in zones:
        try:
            supabase.table("zones").update({
                "polygon":    z.get("polygon", []),
                "active":     z.get("active", True),
                "updated_at": "now()",
            }).eq("name", z["name"]).execute()
        except Exception as exc:
            print(f"Supabase update failed for zone {z['name']}: {exc}")

    return jsonify({"ok": True, "saved": len(zones)})


@app.route("/resolution")
def resolution():
    return jsonify({"width": WORKING_W, "height": WORKING_H})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7070, debug=False)
