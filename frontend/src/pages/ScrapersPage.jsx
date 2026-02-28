import { useState, useEffect } from "react";
import { api } from "../api";

export default function ScrapersPage() {
  const [configs, setConfigs] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    site_name: "",
    base_url: "",
    product_selector: "",
    image_selector: "img",
    name_selector: "h1",
  });
  const [runningId, setRunningId] = useState(null);
  const [runUrl, setRunUrl] = useState("");
  const [results, setResults] = useState(null);

  const load = async () => {
    try {
      const data = await api.listScraperConfigs();
      setConfigs(data);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.addScraperConfig(form);
      setForm({
        site_name: "",
        base_url: "",
        product_selector: "",
        image_selector: "img",
        name_selector: "h1",
      });
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRun = async (configId) => {
    setRunningId(configId);
    setError("");
    setResults(null);
    try {
      const data = await api.runScraper(configId, runUrl, 10);
      setResults(data);
      setRunUrl("");
    } catch (e) {
      setError(e.message);
    } finally {
      setRunningId(null);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Scraper Configs</h1>
        <p>Configure scrapers for furniture websites</p>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="panel" style={{ marginBottom: "1.5rem" }}>
        <h3>Add Scraper Config</h3>
        <form onSubmit={handleAdd}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div className="form-group">
              <label>Site Name</label>
              <input
                required
                placeholder="e.g. Wayfair"
                value={form.site_name}
                onChange={(e) => setForm({ ...form, site_name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Base URL</label>
              <input
                required
                placeholder="https://www.example.com/sofas"
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Product Link Selector (CSS)</label>
              <input
                placeholder="e.g. a.product-card"
                value={form.product_selector}
                onChange={(e) => setForm({ ...form, product_selector: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Image Selector (CSS)</label>
              <input
                placeholder="e.g. img.product-image"
                value={form.image_selector}
                onChange={(e) => setForm({ ...form, image_selector: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Name Selector (CSS)</label>
              <input
                placeholder="e.g. h1.product-title"
                value={form.name_selector}
                onChange={(e) => setForm({ ...form, name_selector: e.target.value })}
              />
            </div>
          </div>
          <button type="submit" className="btn-primary" style={{ marginTop: "0.5rem" }}>
            Save Config
          </button>
        </form>
      </div>

      {configs.length > 0 && (
        <div className="panel">
          <h3>Saved Configs</h3>
          {configs.map((config) => (
            <div
              key={config.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.75rem 0",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <div>
                <strong>{config.site_name}</strong>
                <br />
                <small style={{ color: "var(--text-secondary)" }}>{config.base_url}</small>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <input
                  style={{ width: 250 }}
                  placeholder="Optional: override URL"
                  value={runningId === config.id ? runUrl : ""}
                  onChange={(e) => setRunUrl(e.target.value)}
                />
                <button
                  className="btn-primary btn-sm"
                  onClick={() => handleRun(config.id)}
                  disabled={runningId !== null}
                >
                  {runningId === config.id ? "Running..." : "Run"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {results && (
        <div className="panel" style={{ marginTop: "1.5rem" }}>
          <h3>Scraping Results</h3>
          <p>Scraped {results.scraped} items</p>
          <div className="image-grid" style={{ marginTop: "1rem" }}>
            {results.items?.map((item, i) => (
              <div key={i} className="image-card">
                <img
                  src={api.imageUrl("furniture", item.filename)}
                  alt={item.name}
                  loading="lazy"
                />
                <div className="image-card-info">
                  <h4>{item.name}</h4>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
