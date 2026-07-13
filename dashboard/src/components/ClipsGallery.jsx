import { useState, useEffect } from "react";

function fmtTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

const ZONE_EMOJI = {
  hide:    "🏠",
  food:    "🍽️",
  water:   "💧",
  explore: "🗺️",
  unknown: "❓",
};

export default function ClipsGallery() {
  const [clips,  setClips]  = useState(null);
  const [active, setActive] = useState(null);

  useEffect(() => {
    fetch("/api/clips")
      .then(r => r.json())
      .then(setClips)
      .catch(() => {});
  }, []);

  if (!clips) return <div className="loading">Loading clips…</div>;

  if (clips.length === 0) {
    return (
      <div className="empty">
        No highlight clips yet!<br/>
        Clips are saved when Coco wakes up and starts moving. 🐹
      </div>
    );
  }

  return (
    <div>
      <p className="section-title">{clips.length} highlight clip{clips.length !== 1 ? "s" : ""}</p>

      <div className="clips-grid">
        {clips.map(clip => (
          <div key={clip.id} className="clip-card" onClick={() => setActive(clip)}>
            <div className="clip-thumb">
              {ZONE_EMOJI[clip.trigger_zone] ?? "🐹"}
            </div>
            <div className="clip-info">
              <div className="clip-zone">
                {ZONE_EMOJI[clip.trigger_zone]} {clip.trigger_zone}
              </div>
              <div className="clip-time">{fmtTime(clip.occurred_at)}</div>
              <div className="clip-dur">{clip.duration_seconds}s clip</div>
            </div>
          </div>
        ))}
      </div>

      {active && (
        <div className="modal-overlay" onClick={() => setActive(null)}>
          <div className="modal-inner" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setActive(null)}>✕ close</button>
            <video
              src={`/api/clips/file/${active.filename}`}
              controls
              autoPlay
              style={{ width: "100%", borderRadius: 10 }}
            />
            <p style={{ textAlign: "center", marginTop: 8, color: "#ccc", fontSize: "0.85rem" }}>
              {ZONE_EMOJI[active.trigger_zone]} {active.trigger_zone} — {fmtTime(active.occurred_at)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
