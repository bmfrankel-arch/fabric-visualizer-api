import { useState, useEffect, useRef } from "react";
import { api } from "../api";

export default function VisualizePage() {
  // Fabric state
  const [fabricSearch, setFabricSearch] = useState("");
  const [fabricJacquard, setFabricJacquard] = useState(""); // "" | "yes" | "no"
  const [fabrics, setFabrics] = useState([]);
  const [fabricTotal, setFabricTotal] = useState(0);
  const [fabricLoading, setFabricLoading] = useState(true);
  const [selectedPattern, setSelectedPattern] = useState(null);
  const [selectedColorway, setSelectedColorway] = useState(null);

  // Pillow fabric state
  const [fabricPanelMode, setFabricPanelMode] = useState("body"); // "body" | "pillow"
  const [selectedPillowColorway, setSelectedPillowColorway] = useState(null);

  // Furniture state
  const [retailers, setRetailers] = useState([]);
  const [activeRetailer, setActiveRetailer] = useState(""); // "upload" = custom upload tab
  const [furnitureSearch, setFurnitureSearch] = useState("");
  const [furnitureType, setFurnitureType] = useState("");
  const [furniture, setFurniture] = useState([]);
  const [furnitureTotal, setFurnitureTotal] = useState(0);
  const [furnitureLoading, setFurnitureLoading] = useState(true);
  const [furnitureFilters, setFurnitureFilters] = useState({ types: [] });
  const [selectedFurniture, setSelectedFurniture] = useState(null);

  // Custom frame upload state
  const [uploadDragging, setUploadDragging] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const uploadInputRef = useRef(null);

  // Visualization state
  const [result, setResult] = useState(null);
  const [visualizing, setVisualizing] = useState(false);
  const [error, setError] = useState("");

  // Refinement state
  const [refinePrompt, setRefinePrompt] = useState("");
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState("");

  // AI mode state — default ON; will be forced off if OpenAI isn't available
  const [aiMode, setAiMode] = useState(true);
  const [openaiEnabled, setOpenaiEnabled] = useState(true); // optimistic; health check will correct if unavailable

  const fabricSearchTimer = useRef(null);
  const furnitureSearchTimer = useRef(null);

  // Load health check + retailers on mount
  useEffect(() => {
    api.health().then((h) => {
      setOpenaiEnabled(!!h.openai_enabled);
    }).catch(() => {});

    api.catalogRetailers().then((r) => {
      setRetailers(r);
      if (r.length > 0) setActiveRetailer(r[0].key);
    });
  }, []);

  // If AI becomes unavailable reset mode
  useEffect(() => {
    if (!openaiEnabled) setAiMode(false);
  }, [openaiEnabled]);

  // Load fabrics
  useEffect(() => {
    setFabricLoading(true);
    const params = { limit: "80" };
    if (fabricSearch) params.q = fabricSearch;
    if (fabricJacquard) params.jacquard = fabricJacquard;
    api
      .catalogFabrics(params)
      .then((data) => {
        setFabrics(data.items);
        setFabricTotal(data.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setFabricLoading(false));
  }, [fabricSearch, fabricJacquard]);

  // Load furniture when retailer or filters change
  useEffect(() => {
    if (!activeRetailer || activeRetailer === "upload") return;
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
    if (pattern.image_urls && pattern.image_urls.length > 0) {
      const cw = {
        url: pattern.image_urls[0],
        name: getColorName(pattern.images[0]),
        patternName: pattern.name,
      };
      if (fabricPanelMode === "pillow") {
        // Pre-select first colorway as pillow, but stay in pillow mode so
        // selectColorway() can still correctly route the explicit colorway click.
        setSelectedPillowColorway(cw);
        // Do NOT setFabricPanelMode("body") here — that flip happens in selectColorway().
      } else {
        setSelectedColorway(cw);
      }
    }
  };

  const selectColorway = (pattern, imgUrl, imgFile) => {
    const cw = {
      url: imgUrl,
      name: getColorName(imgFile),
      patternName: pattern.name,
    };
    if (fabricPanelMode === "pillow") {
      setSelectedPillowColorway(cw);
      setFabricPanelMode("body");
    } else {
      setSelectedColorway(cw);
    }
  };

  const getColorName = (filename) => {
    const parts = filename.replace(/\.\w+$/, "").split("-");
    parts.shift();
    return parts.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  };

  const getFurnitureImageUrl = (item) => {
    return item.image_url || item.image || item.thumbnail || "";
  };

  // ── Custom frame upload ──────────────────────────────────────

  const handleFrameFile = async (file) => {
    if (!file || !file.type.startsWith("image/")) {
      setError("Please upload an image file");
      return;
    }
    setUploadLoading(true);
    setError("");
    try {
      const data = await api.uploadCustomFurniture(file);
      const item = {
        name: data.name || "Custom Frame",
        image_url: data.image_url,
        _custom: true,
      };
      setSelectedFurniture(item);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploadLoading(false);
    }
  };

  const handleFrameDrop = (e) => {
    e.preventDefault();
    setUploadDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFrameFile(file);
  };

  // ── Visualize ────────────────────────────────────────────────

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
    setRefinePrompt("");
    setRefineError("");
    const mode = aiMode && openaiEnabled ? "ai" : "cv";
    try {
      const res = await api.visualizeFromUrls(
        selectedColorway.url,
        furnitureImg,
        `${selectedColorway.patternName} - ${selectedColorway.name}`,
        selectedFurniture.name,
        mode,
        selectedPillowColorway?.url || "",
        selectedPillowColorway
          ? `${selectedPillowColorway.patternName} - ${selectedPillowColorway.name}`
          : ""
      );
      setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setVisualizing(false);
    }
  };

  // ── Refine ───────────────────────────────────────────────────

  const handleRefine = async () => {
    if (!result || !refinePrompt.trim()) return;
    setRefining(true);
    setRefineError("");
    try {
      const res = await api.refineVisualization(result.result_filename, refinePrompt);
      setResult((prev) => ({
        ...prev,
        result_filename: res.result_filename,
        result_url: res.result_url,
        mode: "ai",
      }));
      setRefinePrompt("");
    } catch (e) {
      setRefineError(e.message);
    } finally {
      setRefining(false);
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
                  setFabricPanelMode("body");
                }}
              >
                ×
              </button>
            </div>
          ) : (
            <span className="selection-empty">Choose below</span>
          )}
        </div>

        {/* Pillow fabric slot */}
        <div className="selection-slot">
          <span className="selection-label">
            Pillows:
            {!aiMode && <span className="ai-only-tag" title="Pillow fabric only applied in AI mode"> AI</span>}
          </span>
          {selectedPillowColorway ? (
            <div className="selection-chip selection-chip-pillow">
              <img src={selectedPillowColorway.url} alt="" />
              <span>
                {selectedPillowColorway.patternName} — {selectedPillowColorway.name}
              </span>
              <button onClick={() => setSelectedPillowColorway(null)}>×</button>
            </div>
          ) : fabricPanelMode === "pillow" ? (
            <span className="selection-empty selection-empty-active">← Pick a colorway</span>
          ) : (
            <button
              className="selection-add-btn"
              onClick={() => {
                setFabricPanelMode("pillow");
                setSelectedPattern(null);
              }}
            >
              + Add pillow fabric
            </button>
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

        {/* Mode toggle */}
        <div className="mode-toggle" title={!openaiEnabled ? "Add FV_OPENAI_API_KEY to enable AI mode" : ""}>
          <button
            className={`mode-btn ${!aiMode ? "active" : ""}`}
            onClick={() => setAiMode(false)}
          >
            Standard
          </button>
          <button
            className={`mode-btn mode-btn-ai ${aiMode ? "active" : ""}`}
            onClick={() => openaiEnabled && setAiMode(true)}
            disabled={!openaiEnabled}
          >
            ✨ AI
          </button>
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
            <div className="spinner" />
            {aiMode
              ? "Generating AI visualization — this takes 30–60 seconds…"
              : "Applying fabric texture…"}
          </div>
        </div>
      )}
      {result && (
        <div className="result-container">
          <div className="result-header">
            <div>
              <h3 style={{ marginBottom: "0.25rem" }}>Result</h3>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
                {result.fabric_name} on {result.furniture_name}
                {result.pillow_fabric_name && (
                  <span style={{ display: "block", marginTop: "0.15rem" }}>
                    Pillows: {result.pillow_fabric_name}
                  </span>
                )}
                {result.mode === "ai" && (
                  <span className="badge-ai">✨ AI</span>
                )}
              </p>
            </div>
            <a
              href={result.result_url}
              download
              className="btn-secondary"
              style={{ textDecoration: "none", display: "inline-block", alignSelf: "flex-start" }}
            >
              Download
            </a>
          </div>
          <img src={result.result_url} alt="Visualization result" />

          {/* Refinement prompt — only when OpenAI is enabled */}
          {openaiEnabled && (
            <div className="refine-section">
              <p className="refine-label">✨ Refine with AI</p>
              {refineError && (
                <div className="error" style={{ marginBottom: "0.5rem" }}>
                  {refineError}
                </div>
              )}
              <div className="refine-row">
                <input
                  type="text"
                  className="refine-input"
                  placeholder='e.g. "lighten the fabric", "clean up the edges", "change background to white"'
                  value={refinePrompt}
                  onChange={(e) => setRefinePrompt(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleRefine()}
                  disabled={refining}
                />
                <button
                  className="btn-primary refine-btn"
                  onClick={handleRefine}
                  disabled={!refinePrompt.trim() || refining}
                >
                  {refining ? (
                    <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Refining…</>
                  ) : (
                    "Refine"
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Two-panel layout */}
      <div className="catalog-layout">
        {/* LEFT: Fabrics */}
        <div className="catalog-panel">
          <div className="catalog-panel-header">
            <h2>
              {fabricPanelMode === "pillow"
                ? "Select Pillow Fabric"
                : "Dorell Fabrics"}
            </h2>
            {fabricPanelMode === "pillow" ? (
              <button
                className="btn-secondary btn-sm"
                onClick={() => setFabricPanelMode("body")}
              >
                Cancel
              </button>
            ) : (
              <span className="catalog-count">{fabricTotal} patterns</span>
            )}
          </div>

          {/* Pillow mode banner */}
          {fabricPanelMode === "pillow" && (
            <div className="pillow-mode-banner">
              🛋 Selecting <strong>pillow fabric</strong> — pick a colorway below. This fabric will be applied to throw pillows in AI mode.
            </div>
          )}

          <div className="catalog-toolbar">
            <input
              type="text"
              placeholder="Search patterns or colors..."
              onChange={(e) => handleFabricSearch(e.target.value)}
            />
            {/* Jacquard filter chips */}
            <div className="jacquard-filter">
              <button
                className={`jacquard-chip ${fabricJacquard === "" ? "active" : ""}`}
                onClick={() => setFabricJacquard("")}
              >
                All
              </button>
              <button
                className={`jacquard-chip ${fabricJacquard === "yes" ? "active" : ""}`}
                onClick={() => setFabricJacquard(fabricJacquard === "yes" ? "" : "yes")}
              >
                Jacquard
              </button>
              <button
                className={`jacquard-chip ${fabricJacquard === "no" ? "active" : ""}`}
                onClick={() => setFabricJacquard(fabricJacquard === "no" ? "" : "no")}
              >
                Non-Jacquard
              </button>
            </div>
          </div>

          {/* Pattern grid or colorway detail */}
          {selectedPattern ? (
            <div className="colorway-detail">
              <button
                className="btn-back"
                onClick={() => setSelectedPattern(null)}
              >
                ← All patterns
              </button>
              <h3>{selectedPattern.name}</h3>
              <p className="fabric-meta">
                {selectedPattern.content} &middot;{" "}
                {selectedPattern.durability} DR &middot;{" "}
                {selectedPattern.direction}
                {selectedPattern.jacquard && (
                  <span className="badge-jacquard">Jacquard</span>
                )}
              </p>
              <div className="colorway-grid">
                {selectedPattern.image_urls.map((url, i) => {
                  const imgFile = selectedPattern.images[i];
                  const colorName = getColorName(imgFile);
                  const isSelected =
                    fabricPanelMode === "pillow"
                      ? selectedPillowColorway?.url === url
                      : selectedColorway?.url === url;
                  return (
                    <div
                      key={i}
                      className={`colorway-card ${isSelected ? "selected" : ""}`}
                      onClick={() => selectColorway(selectedPattern, url, imgFile)}
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
                    <h4>{p.name}{p.jacquard && <span className="badge-jacquard-sm">J</span>}</h4>
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
            {activeRetailer !== "upload" && (
              <span className="catalog-count">{furnitureTotal} items</span>
            )}
          </div>

          {/* Retailer tabs + Upload tab */}
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
            <button
              className={`retailer-tab retailer-tab-upload ${activeRetailer === "upload" ? "active" : ""}`}
              onClick={() => {
                setActiveRetailer("upload");
                setSelectedFurniture(null);
              }}
            >
              ↑ Upload Frame
            </button>
          </div>

          {/* Upload Frame panel */}
          {activeRetailer === "upload" ? (
            <div className="upload-frame-panel">
              <p className="upload-frame-hint">
                Upload a photo of any furniture frame not listed in the catalogs.
              </p>
              <div
                className={`upload-frame-zone ${uploadDragging ? "dragging" : ""} ${uploadLoading ? "loading" : ""}`}
                onClick={() => !uploadLoading && uploadInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setUploadDragging(true); }}
                onDragLeave={() => setUploadDragging(false)}
                onDrop={handleFrameDrop}
              >
                {uploadLoading ? (
                  <><div className="spinner" /> Uploading…</>
                ) : selectedFurniture?._custom ? (
                  <>
                    <img
                      src={getFurnitureImageUrl(selectedFurniture)}
                      alt={selectedFurniture.name}
                      className="upload-frame-preview"
                    />
                    <span className="upload-frame-name">{selectedFurniture.name}</span>
                    <span className="upload-frame-change">Click or drop to replace</span>
                  </>
                ) : (
                  <>
                    <div className="upload-frame-icon">🖼</div>
                    <p>Click to browse or drag &amp; drop an image</p>
                    <small>JPG, PNG or WebP</small>
                  </>
                )}
              </div>
              <input
                ref={uploadInputRef}
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFrameFile(file);
                  e.target.value = "";
                }}
              />
            </div>
          ) : (
            <>
              <div className="catalog-toolbar">
                <input
                  type="text"
                  placeholder="Search furniture..."
                  onChange={(e) => handleFurnitureSearch(e.target.value)}
                  key={activeRetailer}
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
            </>
          )}
        </div>
      </div>
    </>
  );
}
