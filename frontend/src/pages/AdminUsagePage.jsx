import { useEffect, useState } from "react";

const API = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

export default function AdminUsagePage() {
  const [data, setData] = useState(null);
  const [brand, setBrand] = useState("");
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [brandOptions, setBrandOptions] = useState([]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ days: String(days) });
    if (brand) params.set("brand", brand);
    fetch(`${API}/api/analytics/summary?${params}`, { credentials: "include" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setData(d);
        setError("");
        const seen = new Set();
        for (const row of d.totals) if (row.brand) seen.add(row.brand);
        for (const row of d.sessions) if (row.brand) seen.add(row.brand);
        setBrandOptions((prev) => Array.from(new Set([...prev, ...seen])).sort());
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [brand, days]);

  const eventsByBrand = (() => {
    if (!data) return {};
    const grouped = {};
    for (const row of data.totals) {
      const b = row.brand || "(internal)";
      if (!grouped[b]) grouped[b] = {};
      grouped[b][row.event] = row.count;
    }
    return grouped;
  })();

  const sessionsByBrand = (() => {
    if (!data) return {};
    return Object.fromEntries(
      data.sessions.map((s) => [s.brand || "(internal)", s.sessions])
    );
  })();

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <h1 style={{ marginBottom: "0.25rem" }}>Usage Dashboard</h1>
      <p style={{ color: "#666", marginBottom: "1.5rem", fontSize: "0.875rem" }}>
        Last {data?.window_days ?? days} days
        {brand ? ` — ${brand}` : " — all brands + internal"}
      </p>

      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", alignItems: "center" }}>
        <label style={{ fontSize: "0.85rem" }}>Brand:</label>
        <select value={brand} onChange={(e) => setBrand(e.target.value)} style={{ width: "auto", minWidth: 160 }}>
          <option value="">All</option>
          {brandOptions.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
        <label style={{ fontSize: "0.85rem", marginLeft: "1rem" }}>Days:</label>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: "auto", minWidth: 80 }}>
          <option value={7}>7</option>
          <option value={30}>30</option>
          <option value={90}>90</option>
          <option value={365}>365</option>
        </select>
      </div>

      {error && <div className="error">{error}</div>}
      {loading ? (
        <div>Loading…</div>
      ) : data && (
        <>
          <Section title="Events by brand">
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={th}>Brand</th>
                  <th style={th}>Sessions</th>
                  <th style={th}>Page views</th>
                  <th style={th}>Fabrics</th>
                  <th style={th}>Furniture</th>
                  <th style={th}>Visualize started</th>
                  <th style={th}>Visualize completed</th>
                  <th style={th}>Visualize failed</th>
                  <th style={th}>Refine started</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(eventsByBrand).length === 0 && (
                  <tr><td style={td} colSpan={9}>No events yet.</td></tr>
                )}
                {Object.entries(eventsByBrand).map(([b, evs]) => (
                  <tr key={b}>
                    <td style={td}><strong>{b}</strong></td>
                    <td style={td}>{sessionsByBrand[b] ?? 0}</td>
                    <td style={td}>{evs.page_view ?? 0}</td>
                    <td style={td}>{evs.fabric_selected ?? 0}</td>
                    <td style={td}>{evs.furniture_selected ?? 0}</td>
                    <td style={td}>{evs.visualize_started ?? 0}</td>
                    <td style={td}>{evs.visualize_completed ?? 0}</td>
                    <td style={td}>{evs.visualize_failed ?? 0}</td>
                    <td style={td}>{evs.refine_started ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="Daily activity">
            <table style={tableStyle}>
              <thead>
                <tr><th style={th}>Day</th><th style={th}>Brand</th><th style={th}>Events</th></tr>
              </thead>
              <tbody>
                {data.daily.length === 0 && (
                  <tr><td style={td} colSpan={3}>No activity yet.</td></tr>
                )}
                {data.daily.map((d, i) => (
                  <tr key={i}>
                    <td style={td}>{d.day}</td>
                    <td style={td}>{d.brand || "(internal)"}</td>
                    <td style={td}>{d.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="Recent events (latest 100)">
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={th}>Time</th><th style={th}>Brand</th><th style={th}>Event</th>
                  <th style={th}>Session</th><th style={th}>Payload</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.length === 0 && (
                  <tr><td style={td} colSpan={5}>No events yet.</td></tr>
                )}
                {data.recent.map((r, i) => (
                  <tr key={i}>
                    <td style={td}>{new Date(r.ts * 1000).toLocaleString()}</td>
                    <td style={td}>{r.brand || "(internal)"}</td>
                    <td style={td}>{r.event}</td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: "0.75rem" }}>{(r.session_id || "").slice(0, 8)}</td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: "0.75rem", maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.payload}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section style={{ marginBottom: "2rem" }}>
      <h2 style={{ fontSize: "0.9rem", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#666" }}>{title}</h2>
      {children}
    </section>
  );
}

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.85rem",
  background: "var(--surface, #fff)",
  border: "1px solid var(--border, #e2e0dc)",
  borderRadius: 8,
  overflow: "hidden",
};
const th = {
  textAlign: "left",
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--border, #e2e0dc)",
  background: "var(--bg, #f8f7f4)",
  fontSize: "0.75rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--text-secondary, #666)",
};
const td = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--border, #f0eeea)",
};
