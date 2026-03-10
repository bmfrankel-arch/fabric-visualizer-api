import { useState, useEffect, useRef } from "react";
import { api } from "../api";

export default function FabricsPage() {
  const [fabrics, setFabrics] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedPattern, setSelectedPattern] = useState(null);
  const searchTimer = useRef(null);
  const PAGE_SIZE = 120;

  useEffect(() => {
    setLoading(true);
    const params = { limit: String(PAGE_SIZE) };
    if (search) params.q = search;
    api
      .catalogFabrics(params)
      .then((data) => {
        setFabrics(data.items);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [search]);

  const loadMoreFabrics = () => {
    setLoadingMore(true);
    const params = { limit: String(PAGE_SIZE), offset: String(fabrics.length) };
    if (search) params.q = search;
    api
      .catalogFabrics(params)
      .then((data) => {
        setFabrics((prev) => [...prev, ...data.items]);
      })
      .finally(() => setLoadingMore(false));
  };

  const handleSearch = (val) => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setSearch(val), 300);
  };

  const getColorName = (filename) => {
    const parts = filename.replace(/\.\w+$/, "").split("-");
    parts.shift();
    return parts.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  };

  return (
    <>
      <div className="page-header">
        <h1>Dorell Fabrics Library</h1>
        <p>{total} patterns available</p>
      </div>

      <div className="catalog-toolbar" style={{ padding: 0, marginBottom: "1.5rem" }}>
        <input
          type="text"
          placeholder="Search patterns or colors..."
          onChange={(e) => handleSearch(e.target.value)}
          style={{ maxWidth: 400 }}
        />
      </div>

      {selectedPattern ? (
        <div>
          <button
            className="btn-back"
            onClick={() => setSelectedPattern(null)}
          >
            ← All patterns
          </button>
          <h2 style={{ marginBottom: "0.25rem" }}>{selectedPattern.name}</h2>
          <p className="fabric-meta" style={{ marginBottom: "0.5rem" }}>
            {selectedPattern.content} &middot; {selectedPattern.durability} DR
            &middot; {selectedPattern.direction} &middot;{" "}
            Clean: {selectedPattern.cleanCode}
          </p>
          {selectedPattern.description && (
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "0.85rem",
                marginBottom: "1.5rem",
                maxWidth: 600,
              }}
            >
              {selectedPattern.description}
            </p>
          )}
          <div className="image-grid">
            {selectedPattern.image_urls.map((url, i) => (
              <div key={i} className="image-card">
                <img src={url} alt="" loading="lazy" />
                <div className="image-card-info">
                  <h4>{getColorName(selectedPattern.images[i])}</h4>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : loading ? (
        <div className="loading">
          <div className="spinner" /> Loading fabrics...
        </div>
      ) : (
        <>
          <div className="image-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
            {fabrics.map((p) => (
              <div
                key={p.slug}
                className="image-card"
                onClick={() => setSelectedPattern(p)}
              >
                <img src={p.thumbnail} alt={p.name} loading="lazy" />
                <div className="image-card-info">
                  <h4>{p.name}</h4>
                  <small>
                    {p.images.length} color{p.images.length !== 1 ? "s" : ""}
                    &middot; {p.content}
                  </small>
                </div>
              </div>
            ))}
          </div>
          {fabrics.length < total && (
            <div className="load-more-container">
              <button
                className="btn-load-more"
                onClick={loadMoreFabrics}
                disabled={loadingMore}
              >
                {loadingMore ? (
                  <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Loading…</>
                ) : (
                  `Load More (${fabrics.length} of ${total})`
                )}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
