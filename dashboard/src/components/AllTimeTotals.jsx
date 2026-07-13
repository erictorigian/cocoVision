import { useState, useEffect } from "react";

function fmtHours(secs) {
  const h = Math.round(secs / 3600);
  return h.toLocaleString();
}

function funFact(secs, key) {
  const h = secs / 3600;
  if (key === "sleeping_seconds") {
    const nights = Math.round(h / 8);
    return nights > 0 ? `That's ${nights} full nights of sleep!` : null;
  }
  if (key === "exploring_seconds") {
    const marathons = (h / 4).toFixed(1);
    return h >= 4 ? `Like running ${marathons} hamster marathons!` : null;
  }
  if (key === "eating_seconds" || key === "drinking_seconds") {
    return null;
  }
  return null;
}

const STATS = [
  { key: "sleeping_seconds",  label: "slept",    emoji: "😴", color: "#7c6fcd", unit: "hours" },
  { key: "exploring_seconds", label: "explored", emoji: "🐾", color: "#52b788", unit: "hours" },
  { key: "eating_seconds",    label: "eating",   emoji: "🍽️", color: "#f4845f", unit: "hours" },
  { key: "drinking_seconds",  label: "drinking", emoji: "💧", color: "#4dabf7", unit: "hours" },
];

const VISITS = [
  { key: "food_visits",    label: "food bowl visits",    emoji: "🍽️" },
  { key: "water_visits",   label: "water bottle visits", emoji: "💧" },
  { key: "hide_visits",    label: "trips to her hide",   emoji: "🏠" },
  { key: "explore_visits", label: "exploring sessions",  emoji: "🗺️" },
];

export default function AllTimeTotals() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch("/api/alltime")
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return <div className="loading">Loading all-time records…</div>;

  const days = data.days_tracked || 0;

  return (
    <div>
      <p className="section-title">
        Since we started watching Coco
        {days > 0 ? ` — ${days} day${days !== 1 ? "s" : ""} of data` : ""}
      </p>

      <div className="alltime-grid">
        {STATS.map(s => {
          const h    = fmtHours(data[s.key] || 0);
          const fact = funFact(data[s.key] || 0, s.key);
          return (
            <div key={s.key} className="alltime-card" style={{ "--c": s.color }}>
              <div className="emoji">{s.emoji}</div>
              <div className="big">{h}</div>
              <div className="desc">hours {s.label}</div>
              {fact && <div className="fun">{fact}</div>}
            </div>
          );
        })}
      </div>

      <p className="section-title">All-Time Visit Counts</p>
      <div className="alltime-grid">
        {VISITS.map(v => (
          <div key={v.key} className="alltime-card" style={{ "--c": "#f0a500" }}>
            <div className="emoji">{v.emoji}</div>
            <div className="big">{(data[v.key] || 0).toLocaleString()}</div>
            <div className="desc">{v.label}</div>
          </div>
        ))}
      </div>

      {days === 0 && (
        <div className="empty">No data yet — get the tracker running and check back! 🐹</div>
      )}
    </div>
  );
}
