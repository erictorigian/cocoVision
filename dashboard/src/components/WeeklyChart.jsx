import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const BARS = [
  { key: "sleeping_seconds",  name: "Sleeping",  color: "#7c6fcd" },
  { key: "exploring_seconds", name: "Exploring", color: "#52b788" },
  { key: "eating_seconds",    name: "Eating",    color: "#f4845f" },
  { key: "drinking_seconds",  name: "Drinking",  color: "#4dabf7" },
  { key: "active_seconds",    name: "Active",    color: "#adb5bd" },
];

function shortDay(iso) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "numeric", day: "numeric" });
}

function toHours(secs) {
  return parseFloat((secs / 3600).toFixed(1));
}

function fmtTip(value) {
  const h = Math.floor(value);
  const m = Math.round((value - h) * 60);
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0)           return `${h}h`;
  return `${m}m`;
}

export default function WeeklyChart() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch("/api/weekly")
      .then(r => r.json())
      .then(rows => setData(rows.map(r => ({
        day: shortDay(r.date),
        ...Object.fromEntries(BARS.map(b => [b.key, toHours(r[b.key] || 0)])),
      }))))
      .catch(() => {});
  }, []);

  if (!data) return <div className="loading">Loading weekly data…</div>;

  const hasData = data.some(row => BARS.some(b => row[b.key] > 0));

  return (
    <div>
      <p className="section-title">Last 7 Days</p>

      {!hasData ? (
        <div className="empty">Not enough data yet — come back in a few days! 🐹</div>
      ) : (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="day" tick={{ fontSize: 12 }} />
              <YAxis
                unit="h"
                tick={{ fontSize: 12 }}
                label={{ value: "hours", angle: -90, position: "insideLeft", offset: 10, fontSize: 11, fill: "#888" }}
              />
              <Tooltip
                formatter={(val, name) => [fmtTip(val), name]}
                contentStyle={{ borderRadius: 8, border: "none", boxShadow: "0 2px 12px rgba(0,0,0,0.1)" }}
              />
              <Legend />
              {BARS.map(b => (
                <Bar key={b.key} dataKey={b.key} name={b.name} stackId="a"
                     fill={b.color} radius={[0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
