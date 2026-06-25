const API = import.meta.env.VITE_BACKEND_URL || "";
const API_KEY = import.meta.env.VITE_API_KEY || "";

// Brand mode: when these are set at build time, the UI locks to a single
// retailer and authenticates with X-API-Key against the shared backend.
export const BRAND = {
  key: import.meta.env.VITE_BRAND_KEY || "",
  name: import.meta.env.VITE_BRAND_NAME || "",
  logoUrl: import.meta.env.VITE_BRAND_LOGO_URL || "",
  accent: import.meta.env.VITE_BRAND_ACCENT || "",
};

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  // Fabrics
  listFabrics: (category = "") =>
    request(`/api/fabrics/${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  getFabric: (id) => request(`/api/fabrics/${id}`),
  uploadFabric: (file, name = "", category = "") => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    if (category) form.append("category", category);
    return request("/api/fabrics/", { method: "POST", body: form });
  },
  uploadFabricsBulk: (files, category = "") => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (category) form.append("category", category);
    return request("/api/fabrics/bulk", { method: "POST", body: form });
  },
  deleteFabric: (id) => request(`/api/fabrics/${id}`, { method: "DELETE" }),
  fabricCategories: () => request("/api/fabrics/categories"),

  // Furniture
  listFurniture: (category = "") =>
    request(`/api/furniture/${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  getFurniture: (id) => request(`/api/furniture/${id}`),
  uploadFurniture: (file, name = "", category = "") => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    if (category) form.append("category", category);
    return request("/api/furniture/", { method: "POST", body: form });
  },
  deleteFurniture: (id) => request(`/api/furniture/${id}`, { method: "DELETE" }),

  // Scraper
  scrapeUrl: (url) =>
    request(`/api/scraper/scrape-url?url=${encodeURIComponent(url)}&site_name=manual`, {
      method: "POST",
    }),
  listScraperConfigs: () => request("/api/scraper/configs"),
  addScraperConfig: (config) =>
    request("/api/scraper/configs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  runScraper: (configId, url = "", maxItems = 10) =>
    request(
      `/api/scraper/run/${configId}?url=${encodeURIComponent(url)}&max_items=${maxItems}`,
      { method: "POST" }
    ),

  // Visualize
  visualize: (fabricId, furnitureId) =>
    request("/api/visualize/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fabric_id: fabricId, furniture_id: furnitureId }),
    }),
  visualizationHistory: () => request("/api/visualize/history"),

  // Catalog
  catalogFabrics: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/catalog/fabrics${qs ? `?${qs}` : ""}`);
  },
  catalogFabric: (slug) => request(`/api/catalog/fabrics/${slug}`),
  catalogFabricsFilters: () => request("/api/catalog/fabrics-filters"),
  catalogRetailers: () => request("/api/catalog/retailers"),
  catalogFurniture: (retailer, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/catalog/furniture/${retailer}${qs ? `?${qs}` : ""}`);
  },
  catalogFurnitureFilters: (retailer) =>
    request(`/api/catalog/furniture/${retailer}/filters`),

  // Poll an async AI job (visualize/refine) until it finishes.
  // The server runs slow OpenAI work in the background and returns a job_id;
  // we poll /status until it's done rather than holding one long request open.
  pollJob: async (jobId, { interval = 3000, timeout = 360000 } = {}) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, interval));
      const job = await request(`/api/visualize/status/${jobId}`);
      if (job.status === "done") return job;
      if (job.status === "error") throw new Error(job.error || "AI job failed");
    }
    throw new Error("Timed out waiting for the AI result.");
  },

  // Visualize from URLs
  // mode: "cv" (local pipeline, synchronous) | "ai" (OpenAI gpt-image-2, async job)
  // pillowFabricUrl/pillowFabricName: optional second fabric applied to throw pillows (AI mode only)
  visualizeFromUrls: async (fabricUrl, furnitureUrl, fabricName = "", furnitureName = "", mode = "cv", pillowFabricUrl = "", pillowFabricName = "") => {
    const resp = await request("/api/visualize/from-urls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fabric_url: fabricUrl,
        furniture_url: furnitureUrl,
        fabric_name: fabricName,
        furniture_name: furnitureName,
        mode,
        pillow_fabric_url: pillowFabricUrl,
        pillow_fabric_name: pillowFabricName,
      }),
    });
    // AI mode returns a job to poll; CV mode returns the result inline.
    return resp && resp.job_id ? api.pollJob(resp.job_id) : resp;
  },

  // Refine an existing result with a custom prompt (AI only — async job)
  refineVisualization: async (resultFilename, prompt) => {
    const resp = await request("/api/visualize/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result_filename: resultFilename, prompt }),
    });
    return resp && resp.job_id ? api.pollJob(resp.job_id) : resp;
  },

  // Upload a custom furniture frame photo
  uploadCustomFurniture: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/catalog/upload-furniture", { method: "POST", body: form });
  },

  // Health
  health: () => request("/api/health"),

  // Image URLs
  imageUrl: (type, filename) => `${API}/uploads/${type}/${filename}`,
  resultUrl: (filename) => `${API}/uploads/results/${filename}`,
};
