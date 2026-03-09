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
  const [detailItem, setDetailItem] = useState(null);
  const searchTimer = useRef(null);
  const retailerScrollRef = useRef(null);

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

      <div className="retailer-tabs-wrapper" style={{ marginBottom: "1rem" }}>
        <button className="retailer-tabs-arrow" onClick={() => retailerScrollRef.current?.scrollBy({ left: -200, behavior: "smooth" })} aria-label="Scroll left">&#8249;</button>
        <div className="retailer-tabs" ref={retailerScrollRef}>
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
        <button className="retailer-tabs-arrow" onClick={() => retailerScrollRef.current?.scrollBy({ left: 200, behavior: "smooth" })} aria-label="Scroll right">&#8250;</button>
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
              <div key={`${item.sku || item.name}-${i}`} className="image-card" onClick={() => setDetailItem(item)}>
                {imgUrl ? (
                  <img src={imgUrl} alt={item.name} loading="lazy" />
                ) : (
                  <div style={{
                    width: "100%",
                    height: 200,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--text-secondary)",
                    fontSize: "0.75rem",
                    background: "#f5f5f5",
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

      {/* Furniture Detail Modal */}
      {detailItem && (
        <div className="furniture-detail-modal" onClick={() => setDetailItem(null)}>
          <div className="furniture-detail-content" onClick={(e) => e.stopPropagation()}>
            <button className="furniture-detail-close" onClick={() => setDetailItem(null)}>&times;</button>
            {getImg(detailItem) && (
              <img src={getImg(detailItem)} alt={detailItem.name} />
            )}
            <div className="furniture-detail-info">
              <h2>{detailItem.name}</h2>
              <div className="furniture-detail-meta">
                {detailItem.price && (
                  <span className="furniture-detail-price">
                    ${detailItem.price.toLocaleString()}
                    {detailItem.compare_at_price && detailItem.compare_at_price > detailItem.price && (
                      <s>${detailItem.compare_at_price.toLocaleString()}</s>
                    )}
                  </span>
                )}
                {detailItem.collection && <span className="furniture-detail-tag">{detailItem.collection}</span>}
                {detailItem.type && <span className="furniture-detail-tag">{detailItem.type}</span>}
                {detailItem.material && <span className="furniture-detail-tag">{detailItem.material}</span>}
              </div>
              {detailItem.url && (
                <a
                  href={detailItem.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="furniture-detail-link"
                >
                  View on {retailers.find((r) => r.key === activeRetailer)?.name || "retailer"} &rarr;
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
