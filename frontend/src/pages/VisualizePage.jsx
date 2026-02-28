import { useState, useEffect, useRef } from "react";
import { api } from "../api";

export default function VisualizePage() {
  // Fabric state
  const [fabricSearch, setFabricSearch] = useState("");
  const [fabrics, setFabrics] = useState([]);
  const [fabricTotal, setFabricTotal] = useState(0);
  const [fabricLoading, setFabricLoading] = useState(true);
  const [selectedPattern, setSelectedPattern] = useState(null);
  const [selectedColorway, setSelectedColorway] = useState(null);

  // Furniture state
  const [retailers, setRetailers] = useState([]);
  const [activeRetailer, setActiveRetailer] = useState("");
  const [furnitureSearch, setFurnitureSearch] = useState("");
  const [furnitureType, setFurnitureType] = useState("");
  const [furniture, setFurniture] = useState([]);
  const [furnitureTotal, setFurnitureTotal] = useState(0);
  const [furnitureLoading, setFurnitureLoading] = useState(true);
  const [furnitureFilters, setFurnitureFilters] = useState({ types: [] });
  const [selectedFurniture, setSelectedFurniture] = useState(null);

  // Visualization state
  const [result, setResult] = useState(null);
  const [visualizing, setVisualizing] = useState(false);
  const [error, setError] = useState("");

  const fabricSearchTimer = useRef(null);
  const furnitureSearchTimer = useRef(null);

  // Load retailers on mount
  useEffect(() => {
    api.catalogRetailers().then((r) => {
      setRetailers(r);
      if (r.length > 0) setActiveRetailer(r[0].key);
    });
  }, []);

  // Load fabrics
  useEffect(() => {
    setFabricLoading(true);
    const params = { limit: "80" };
    if (fabricSearch) params.q = fabricSearch;
    api
      .catalogFabrics(params)
      .then((data) => {
        setFabrics(data.items);
        setFabricTotal(data.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setFabricLoading(false));
  }, [fabricSearch]);

  // Load furniture when retailer or filters change
  useEffect(() => {
    if (!activeRetailer) return;
    setFurnitureLoading(true);
    const params = { limit: "80" };
    if (furnitureSearch) params.q = furnitureSearch;
    if (furnitureType) params.category = furnitureType;
    Promise.all([
      api.catalogFurniture(activeRetailer, params),
      api.catalogFurnitureFilters(activeRetailer),
    ])
      .then(([data, filters]) => {
        setFurniture(data.items);
        setFurnitureTotal(data.total);
        setFurnitureFilters(filters);
      })
      .catch((e) => setError(e.message))
      .finally(() => setFurnitureLoading(false));
  }, [activeRetailer, furnitureSearch, furnitureType]);

  const handleFabricSearch = (val) => {
    clearTimeout(fabricSearchTimer.current);
    fabricSearchTimer.current = setTimeout(() => setFabricSearch(val), 300);
  };

  const handleFurnitureSearch = (val) => {
    clearTimeout(furnitureSearchTimer.current);
    furnitureSearchTimer.current = setTimeout(
      () => setFurnitureSearch(val),
      300
    );
  };

  const selectPattern = (pattern) => {
    setSelectedPattern(pattern);
    // Auto-select first colorway
    if (pattern.image_urls && pattern.image_urls.length > 0) {
      setSelectedColorway({
        url: pattern.image_urls[0],
        name: getColorName(pattern.images[0]),
        patternName: pattern.name,
      });
    }
  };

  const selectColorway = (pattern, imgUrl, imgFile) => {
    setSelectedColorway({
      url: imgUrl,
      name: getColorName(imgFile),
      patternName: pattern.name,
    });
  };

  const getColorName = (filename) => {
    // "ace-bone.jpg" -> "Bone"
    const parts = filename.replace(/\.\w+$/, "").split("-");
    parts.shift(); // remove pattern name prefix
    return parts.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  };

  const getFurnitureImageUrl = (item) => {
    return item.image_url || item.image || item.thumbnail || "";
  };

  const handleVisualize = async () => {
    if (!selectedColorway || !selectedFurniture) return;
    const furnitureImg = getFurnitureImageUrl(selectedFurniture);
    if (!furnitureImg) {
      setError("Selected furniture has no image");
      return;
    }
    setVisualizing(true);
    setError("");
    setResult(null);
    try {
      const res = await api.visualizeFromUrls(
        selectedColorway.url,
        furnitureImg,
        `${selectedColorway.patternName} - ${selectedColorway.name}`,
        selectedFurniture.name
      );
      setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setVisualizing(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Fabric Visualizer</h1>
        <p>
          Select a Dorell fabric and a furniture piece, then apply the fabric to
          see it on the frame
        </p>
      </div>

      {error && <div className="error">{error}</div>}

      {/* Selection summary bar */}
      <div className="selection-bar">
        <div className="selection-slot">
          <span className="selection-label">Fabric:</span>
          {selectedColorway ? (
            <div className="selection-chip">
              <img src={selectedColorway.url} alt="" />
              <span>
                {selectedColorway.patternName} — {selectedColorway.name}
              </span>
              <button
                onClick={() => {
                  setSelectedColorway(null);
                  setSelectedPattern(null);
                }}
              >
                ×
              </button>
            </div>
          ) : (
            <span className="selection-empty">Choose below</span>
          )}
        </div>
        <div className="selection-slot">
          <span className="selection-label">Furniture:</span>
          {selectedFurniture ? (
            <div className="selection-chip">
              {getFurnitureImageUrl(selectedFurniture) && (
                <img src={getFurnitureImageUrl(selectedFurniture)} alt="" />
              )}
              <span>{selectedFurniture.name}</span>
              <button onClick={() => setSelectedFurniture(null)}>×</button>
            </div>
          ) : (
            <span className="selection-empty">Choose below</span>
          )}
        </div>
        <button
          className="btn-primary btn-visualize"
          onClick={handleVisualize}
          disabled={!selectedColorway || !selectedFurniture || visualizing}
        >
          {visualizing ? "Applying..." : "Apply Fabric"}
        </button>
      </div>

      {/* Result */}
      {visualizing && (
        <div className="result-container">
          <div className="loading">
            <div className="spinner" /> Applying fabric texture...
          </div>
        </div>
      )}
      {result && (
        <div className="result-container">
          <h3 style={{ marginBottom: "0.5rem" }}>Result</h3>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginBottom: "1rem" }}>
            {result.fabric_name} on {result.furniture_name}
          </p>
          <img src={result.result_url} alt="Visualization result" />
          <div style={{ marginTop: "1rem" }}>
            <a
              href={result.result_url}
              download
              className="btn-secondary"
              style={{ textDecoration: "none", display: "inline-block" }}
            >
              Download
            </a>
          </div>
        </div>
      )}

      {/* Two-panel layout */}
      <div className="catalog-layout">
        {/* LEFT: Fabrics */}
        <div className="catalog-panel">
          <div className="catalog-panel-header">
            <h2>Dorell Fabrics</h2>
            <span className="catalog-count">{fabricTotal} patterns</span>
          </div>
          <div className="catalog-toolbar">
            <input
              type="text"
              placeholder="Search patterns or colors..."
              onChange={(e) => handleFabricSearch(e.target.value)}
            />
          </div>

          {/* Pattern grid or colorway detail */}
          {selectedPattern ? (
            <div className="colorway-detail">
              <button
                className="btn-back"
                onClick={() => {
                  setSelectedPattern(null);
                }}
              >
                ← All patterns
              </button>
              <h3>{selectedPattern.name}</h3>
              <p className="fabric-meta">
                {selectedPattern.content} &middot;{" "}
                {selectedPattern.durability} DR &middot;{" "}
                {selectedPattern.direction}
              </p>
              <div className="colorway-grid">
                {selectedPattern.image_urls.map((url, i) => {
                  const imgFile = selectedPattern.images[i];
                  const colorName = getColorName(imgFile);
                  const isSelected = selectedColorway?.url === url;
                  return (
                    <div
                      key={i}
                      className={`colorway-card ${isSelected ? "selected" : ""}`}
                      onClick={() =>
                        selectColorway(selectedPattern, url, imgFile)
                      }
                    >
                      <img src={url} alt={colorName} loading="lazy" />
                      <span>{colorName}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : fabricLoading ? (
            <div className="loading">
              <div className="spinner" /> Loading...
            </div>
          ) : (
            <div className="pattern-grid">
              {fabrics.map((p) => (
                <div
                  key={p.slug}
                  className="pattern-card"
                  onClick={() => selectPattern(p)}
                >
                  <img src={p.thumbnail} alt={p.name} loading="lazy" />
                  <div className="pattern-card-info">
                    <h4>{p.name}</h4>
                    <small>
                      {p.images.length} color{p.images.length !== 1 ? "s" : ""}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* RIGHT: Furniture */}
        <div className="catalog-panel">
          <div className="catalog-panel-header">
            <h2>Furniture</h2>
            <span className="catalog-count">{furnitureTotal} items</span>
          </div>

          {/* Retailer tabs */}
          <div className="retailer-tabs">
            {retailers.map((r) => (
              <button
                key={r.key}
                className={`retailer-tab ${activeRetailer === r.key ? "active" : ""}`}
                onClick={() => {
                  setActiveRetailer(r.key);
                  setFurnitureType("");
                  setFurnitureSearch("");
                  setSelectedFurniture(null);
                }}
              >
                {r.name}
              </button>
            ))}
          </div>

          <div className="catalog-toolbar">
            <input
              type="text"
              placeholder="Search furniture..."
              onChange={(e) => handleFurnitureSearch(e.target.value)}
              key={activeRetailer} // reset input when switching tabs
            />
            {furnitureFilters.types && furnitureFilters.types.length > 0 && (
              <select
                value={furnitureType}
                onChange={(e) => setFurnitureType(e.target.value)}
              >
                <option value="">All types</option>
                {furnitureFilters.types.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
          </div>

          {furnitureLoading ? (
            <div className="loading">
              <div className="spinner" /> Loading...
            </div>
          ) : (
            <div className="furniture-grid">
              {furniture.map((item, i) => {
                const imgUrl = getFurnitureImageUrl(item);
                const isSelected = selectedFurniture === item;
                return (
                  <div
                    key={`${item.sku || item.name}-${i}`}
                    className={`furniture-card ${isSelected ? "selected" : ""}`}
                    onClick={() => setSelectedFurniture(item)}
                  >
                    {imgUrl ? (
                      <img src={imgUrl} alt={item.name} loading="lazy" />
                    ) : (
                      <div className="no-image">No image</div>
                    )}
                    <div className="furniture-card-info">
                      <h4>{item.name}</h4>
                      {item.price && (
                        <span className="price">
                          ${item.price.toLocaleString()}
                          {item.compare_at_price &&
                            item.compare_at_price > item.price && (
                              <s>${item.compare_at_price.toLocaleString()}</s>
                            )}
                        </span>
                      )}
                      {item.collection && (
                        <small className="collection">{item.collection}</small>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
