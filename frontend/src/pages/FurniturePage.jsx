import { useState, useEffect, useRef } from "react";
import { api } from "../api";

export default function FurniturePage() {
  const [retailers, setRetailers] = useState([]);
  const [activeRetailer, setActiveRetailer] = useState("");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [filters, setFilters] = useState({ types: [], collections: [] });
  const searchTimer = useRef(null);

  useEffect(() => {
    api.catalogRetailers().then((r) => {
      setRetailers(r);
      if (r.length > 0) setActiveRetailer(r[0].key);
    });
  }, []);

  useEffect(() => {
    if (!activeRetailer) return;
    setLoading(true);
    const params = { limit: "120" };
    if (search) params.q = search;
    if (typeFilter) params.category = typeFilter;
    Promise.all([
      api.catalogFurniture(activeRetailer, params),
      api.catalogFurnitureFilters(activeRetailer),
    ])
      .then(([data, f]) => {
        setItems(data.items);
        setTotal(data.total);
        setFilters(f);
      })
      .finally(() => setLoading(false));
  }, [activeRetailer, search, typeFilter]);

  const handleSearch = (val) => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setSearch(val), 300);
  };

  const getImg = (item) => item.image_url || item.image || item.thumbnail || "";

  return (
    <>
      <div className="page-header">
        <h1>Furniture Catalog</h1>
        <p>{total} items from {retailers.find((r) => r.key === activeRetailer)?.name || "..."}</p>
      </div>

      <div className="retailer-tabs" style={{ borderBottom: "1px solid var(--border)", marginBottom: "1rem" }}>
        {retailers.map((r) => (
          <button
            key={r.key}
            className={`retailer-tab ${activeRetailer === r.key ? "active" : ""}`}
            onClick={() => {
              setActiveRetailer(r.key);
              setTypeFilter("");
              setSearch("");
            }}
          >
            {r.name}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <input
          type="text"
          placeholder="Search furniture..."
          onChange={(e) => handleSearch(e.target.value)}
          style={{ maxWidth: 300 }}
          key={activeRetailer}
        />
        {filters.types.length > 0 && (
          <select
            style={{ width: "auto", minWidth: 130 }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            {filters.types.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
        <span style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
          {total} items
        </span>
      </div>

      {loading ? (
        <div className="loading">
          <div className="spinner" /> Loading...
        </div>
      ) : (
        <div className="image-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
          {items.map((item, i) => {
            const imgUrl = getImg(item);
            return (
              <div key={`${item.sku || item.name}-${i}`} className="image-card">
                {imgUrl ? (
                  <img src={imgUrl} alt={item.name} loading="lazy" />
                ) : (
                  <div style={{
                    width: "100%",
                    height: 160,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--text-secondary)",
                    fontSize: "0.75rem",
                    background: "var(--bg)",
                  }}>
                    No image
                  </div>
                )}
                <div className="image-card-info">
                  <h4>{item.name}</h4>
                  {item.price && (
                    <small style={{ color: "var(--accent)", fontWeight: 600 }}>
                      ${item.price.toLocaleString()}
                      {item.compare_at_price && item.compare_at_price > item.price && (
                        <s style={{ color: "var(--text-secondary)", fontWeight: 400, marginLeft: 4 }}>
                          ${item.compare_at_price.toLocaleString()}
                        </s>
                      )}
                    </small>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
