const API = import.meta.env.VITE_BACKEND_URL || "";

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
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

  // Visualize from URLs
  visualizeFromUrls: (fabricUrl, furnitureUrl, fabricName = "", furnitureName = "") =>
    request("/api/visualize/from-urls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fabric_url: fabricUrl,
        furniture_url: furnitureUrl,
        fabric_name: fabricName,
        furniture_name: furnitureName,
      }),
    }),

  // Health
  health: () => request("/api/health"),

  // Image URLs
  imageUrl: (type, filename) => `${API}/uploads/${type}/${filename}`,
  resultUrl: (filename) => `${API}/uploads/results/${filename}`,
};
