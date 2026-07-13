"""
Coco Cam — API layer.
Thin FastAPI service between Supabase and the dashboard.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from supabase import create_client

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]
CLIPS_DIR     = Path(os.environ.get("CLIPS_DIR",      "/clips"))
SNAPSHOT_PATH = Path(os.environ.get("SNAPSHOT_PATH",  "/snapshots/current.jpg"))
STATUS_PATH   = Path(os.environ.get("STATUS_PATH",    "/snapshots/status.json"))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Coco Cam API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}

# ── Live view ─────────────────────────────────────────────────────────────────

@app.get("/snapshot")
def snapshot():
    if not SNAPSHOT_PATH.exists():
        raise HTTPException(503, "No snapshot yet — detector may still be starting up")
    return FileResponse(str(SNAPSHOT_PATH), media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


@app.get("/status")
def status():
    if not STATUS_PATH.exists():
        return {"current_state": "unknown", "zone": None,
                "state_duration_seconds": 0, "motion_px": 0, "timestamp": None}
    return JSONResponse(json.loads(STATUS_PATH.read_text()))

# ── Events ────────────────────────────────────────────────────────────────────

@app.get("/events")
def recent_events(limit: int = 50):
    rows = (
        supabase.table("events")
        .select("*")
        .order("occurred_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    return rows

# ── Daily summary ─────────────────────────────────────────────────────────────

@app.get("/daily/{day}")
def daily(day: str):
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    rows = (
        supabase.table("daily_summaries")
        .select("*")
        .eq("date", day)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else _empty_summary(day)


@app.get("/daily")
def today_summary():
    return daily(date.today().isoformat())

# ── All-time totals ───────────────────────────────────────────────────────────

@app.get("/alltime")
def alltime():
    rows = supabase.table("daily_summaries").select("*").execute().data
    totals = {
        "sleeping_seconds":  0,
        "exploring_seconds": 0,
        "eating_seconds":    0,
        "drinking_seconds":  0,
        "active_seconds":    0,
        "hidden_seconds":    0,
        "food_visits":       0,
        "water_visits":      0,
        "hide_visits":       0,
        "explore_visits":    0,
        "days_tracked":      len(rows),
    }
    for r in rows:
        for k in totals:
            if k != "days_tracked":
                totals[k] += r.get(k, 0)
    return totals

# ── Weekly trend ──────────────────────────────────────────────────────────────

@app.get("/weekly")
def weekly():
    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    rows  = (
        supabase.table("daily_summaries")
        .select("*")
        .in_("date", dates)
        .order("date")
        .execute()
        .data
    )
    by_date = {r["date"]: r for r in rows}
    return [by_date.get(d, _empty_summary(d)) for d in dates]

# ── Clips ─────────────────────────────────────────────────────────────────────

@app.get("/clips")
def list_clips(limit: int = 50, offset: int = 0):
    rows = (
        supabase.table("clips")
        .select("*")
        .order("occurred_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data
    )
    return rows


@app.get("/clips/file/{filename}")
def serve_clip(filename: str):
    # Basic path safety — reject any traversal attempts
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")
    path = CLIPS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Clip not found")
    return FileResponse(str(path), media_type="video/mp4")

# ── Zones ─────────────────────────────────────────────────────────────────────

@app.get("/zones")
def zones():
    return supabase.table("zones").select("*").order("name").execute().data

# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty_summary(day: str) -> dict:
    return {
        "date": day,
        "sleeping_seconds": 0, "exploring_seconds": 0,
        "eating_seconds": 0,   "drinking_seconds": 0,
        "active_seconds": 0,   "hidden_seconds": 0,
        "food_visits": 0,      "water_visits": 0,
        "hide_visits": 0,      "explore_visits": 0,
    }
