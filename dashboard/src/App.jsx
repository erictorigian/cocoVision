import { useState, useEffect } from "react";
import DailySummary  from "./components/DailySummary.jsx";
import AllTimeTotals from "./components/AllTimeTotals.jsx";
import WeeklyChart   from "./components/WeeklyChart.jsx";
import ClipsGallery  from "./components/ClipsGallery.jsx";
import LiveView      from "./components/LiveView.jsx";

const TABS = [
  { id: "today",   label: "🌞 Today" },
  { id: "alltime", label: "🏆 All Time" },
  { id: "weekly",  label: "📈 This Week" },
  { id: "clips",   label: "🎬 Clips" },
  { id: "live",    label: "📹 Live" },
];

const STATE_COLORS = {
  sleeping:  "#7c6fcd",
  exploring: "#52b788",
  eating:    "#f4845f",
  drinking:  "#4dabf7",
  active:    "#adb5bd",
  unknown:   "#adb5bd",
};

const STATE_LABELS = {
  sleeping:  "Sleeping 😴",
  exploring: "Exploring 🐾",
  eating:    "Eating 🍽️",
  drinking:  "Drinking 💧",
  active:    "Active 🐹",
  unknown:   "Checking in…",
};

function useStatus() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    const poll = () =>
      fetch("/api/status")
        .then(r => r.json())
        .then(setStatus)
        .catch(() => {});
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);
  return status;
}

export default function App() {
  const [tab, setTab]  = useState("today");
  const status         = useStatus();
  const state          = status?.current_state ?? "unknown";
  const color          = STATE_COLORS[state] ?? "#adb5bd";
  const label          = STATE_LABELS[state] ?? "Checking in…";

  return (
    <div>
      <header className="header">
        <h1>🐹 Coco Cam</h1>
        <div className="status-pill" style={{ "--c": color }}>
          <span className="status-dot" style={{ background: color }} />
          {label}
        </div>
      </header>

      <nav className="tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            className={"tab" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === "today"   && <DailySummary />}
        {tab === "alltime" && <AllTimeTotals />}
        {tab === "weekly"  && <WeeklyChart />}
        {tab === "clips"   && <ClipsGallery />}
        {tab === "live"    && <LiveView status={status} />}
      </main>
    </div>
  );
}
