import { useState, useEffect, useRef } from "react";

const STATE_COLORS = {
  sleeping:  "#7c6fcd",
  exploring: "#52b788",
  eating:    "#f4845f",
  drinking:  "#4dabf7",
  active:    "#adb5bd",
  unknown:   "#adb5bd",
};

const STATE_MSG = {
  sleeping:  "Coco is sleeping 😴",
  exploring: "Coco is exploring! 🐾",
  eating:    "Coco is eating! 🍽️",
  drinking:  "Coco is drinking 💧",
  active:    "Coco is up and about! 🐹",
  unknown:   "Checking on Coco…",
};

function fmtDuration(secs) {
  if (!secs) return "just now";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function LiveView({ status }) {
  const [imgSrc, setImgSrc] = useState("/api/snapshot");
  const timerRef = useRef(null);

  useEffect(() => {
    const refresh = () => setImgSrc("/api/snapshot?t=" + Date.now());
    timerRef.current = setInterval(refresh, 3000);
    return () => clearInterval(timerRef.current);
  }, []);

  const state    = status?.current_state ?? "unknown";
  const color    = STATE_COLORS[state] ?? "#adb5bd";
  const msg      = STATE_MSG[state] ?? "Checking on Coco…";
  const duration = status?.state_duration_seconds ?? 0;
  const zone     = status?.zone;

  return (
    <div>
      <p className="section-title">Live Camera</p>

      <div className="live-wrap">
        <img
          className="live-img"
          src={imgSrc}
          alt="Live camera view"
          onError={() => setImgSrc("/api/snapshot")}
        />

        <div className="live-state" style={{ "--c": color, background: color }}>
          {msg}
        </div>

        <p className="live-duration">
          {duration > 0
            ? `For the last ${fmtDuration(duration)}${zone ? ` · zone: ${zone}` : ""}`
            : "Just switched states"}
        </p>

        <p style={{ marginTop: 12, fontSize: "0.78rem", color: "#bbb" }}>
          Refreshes every 3 seconds
        </p>
      </div>
    </div>
  );
}
