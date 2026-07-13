import { useState, useEffect } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

const STATES = [
  { key: "sleeping_seconds",  label: "Sleeping",  emoji: "😴", color: "#7c6fcd" },
  { key: "exploring_seconds", label: "Exploring", emoji: "🐾", color: "#52b788" },
  { key: "eating_seconds",    label: "Eating",    emoji: "🍽️", color: "#f4845f" },
  { key: "drinking_seconds",  label: "Drinking",  emoji: "💧", color: "#4dabf7" },
  { key: "active_seconds",    label: "Active",    emoji: "🐹", color: "#adb5bd" },
  { key: "hidden_seconds",    label: "Hidden",    emoji: "🌿", color: "#b5885e" },
];

const VISITS = [
  { key: "food_visits",    label: "Food bowl visits",   emoji: "🍽️" },
  { key: "water_visits",   label: "Water bottle visits", emoji: "💧" },
  { key: "hide_visits",    label: "Hide box visits",     emoji: "🏠" },
  { key: "explore_visits", label: "Exploring visits",    emoji: "🗺️" },
];

function fmtDuration(secs) {
  if (!secs) return "0 min";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (h > 0 && m > 0) return `${h} hr ${m} min`;
  if (h > 0)           return `${h} hr`;
  return `${m} min`;
}

function todayLabel() {
  return new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

export default function DailySummary() {
  const [data,  setData]  = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/daily")
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message));
  }, []);

  if (error) return <div className="empty">Couldn't load today's data (API error: {error}). Check that the api container is running.</div>;
  if (!data)  return <div className="loading">Loading today's data…</div>;

  const pieData = STATES
    .map(s => ({ name: s.label, value: data[s.key] || 0, color: s.color, emoji: s.emoji }))
    .filter(d => d.value > 0);

  const totalTracked = STATES.reduce((sum, s) => sum + (data[s.key] || 0), 0);

  return (
    <div>
      <p className="section-title">{todayLabel()}</p>

      <div className="stat-grid">
        {STATES.map(s => (
          <div key={s.key} className="stat-card" style={{ "--c": s.color }}>
            <span className="emoji">{s.emoji}</span>
            <span className="label">{s.label}</span>
            <span className="value">{fmtDuration(data[s.key] || 0)}</span>
          </div>
        ))}
      </div>

      {totalTracked > 0 && (
        <div className="chart-wrap">
          <p className="section-title" style={{ marginBottom: 16 }}>Today's Breakdown</p>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%" cy="50%"
                innerRadius={60}
                outerRadius={95}
                paddingAngle={3}
                dataKey="value"
              >
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => fmtDuration(value)}
                contentStyle={{ borderRadius: 8, border: "none", boxShadow: "0 2px 12px rgba(0,0,0,0.1)" }}
              />
              <Legend formatter={(val, entry) => `${entry.payload.emoji} ${val}`} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="section-title">Visit Counts</p>
      <div className="stat-grid">
        {VISITS.map(v => (
          <div key={v.key} className="stat-card" style={{ "--c": "#f0a500" }}>
            <span className="emoji">{v.emoji}</span>
            <span className="label">{v.label}</span>
            <span className="value">{data[v.key] || 0}×</span>
          </div>
        ))}
      </div>

      {totalTracked === 0 && (
        <div className="empty">
          No activity logged yet today — check back soon! 🐹
        </div>
      )}
    </div>
  );
}
